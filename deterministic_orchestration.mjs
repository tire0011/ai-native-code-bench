#!/usr/bin/env node
/** Deterministic, serial Roslyn MCP orchestration. No model selects tools. */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";
import { spawn } from "node:child_process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
export const REQUIRED_TOOLS = Object.freeze([
  "load_solution",
  "go_to_definition",
  "find_references",
]);

export class ToolCallError extends Error {
  constructor(tool, message) {
    super(`${tool}: ${message}`);
    this.name = "ToolCallError";
    this.tool = tool;
  }
}

function textContent(result) {
  return (Array.isArray(result?.content) ? result.content : [])
    .filter((part) => part?.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n");
}

export function decodeToolResult(tool, result) {
  if (result?.isError) {
    throw new ToolCallError(tool, textContent(result) || "tool returned isError");
  }
  if (result?.structuredContent && typeof result.structuredContent === "object") {
    return result.structuredContent;
  }
  const text = textContent(result);
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object") {
      throw new ToolCallError(tool, "result must be a JSON object");
    }
    return parsed;
  } catch (error) {
    if (error instanceof ToolCallError) throw error;
    // Roslyn uses plain-text success/status messages for some tools (notably load_solution).
    return { text };
  }
}

export function resultItems(payload) {
  let current = payload;
  for (let depth = 0; depth < 3 && current && typeof current === "object"; depth += 1) {
    if (Array.isArray(current.items)) return current.items;
    current = current.result;
  }
  return [];
}

export function resultTotal(payload) {
  let current = payload;
  for (let depth = 0; depth < 3 && current && typeof current === "object"; depth += 1) {
    if (Number.isInteger(current.totalCount)) return current.totalCount;
    current = current.result;
  }
  return resultItems(payload).length;
}

export function publicFile(file, fixtureRoot) {
  if (typeof file !== "string" || !file) return null;
  const resolved = path.resolve(fixtureRoot, file);
  const relative = path.relative(fixtureRoot, resolved);
  if (relative && !relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative)) {
    return relative.split(path.sep).join("/");
  }
  return "<external>";
}

export function publicPaths(payload, fixtureRoot, limit = 50) {
  return resultItems(payload)
    .slice(0, limit)
    .map((item) => publicFile(
      item?.file ?? item?.path ?? item?.filePath ?? item?.document ?? item?.sourceFile,
      fixtureRoot,
    ))
    .filter(Boolean);
}

async function callSerial(client, name, args, options) {
  const { timeoutMs, calls, rawCalls } = options;
  const started = performance.now();
  const publicArgs = structuredClone(args);
  if (publicArgs.path) publicArgs.path = "<solution>";
  const base = { tool: name, arguments: publicArgs };
  let response;
  try {
    response = await client.callTool(
      { name, arguments: args },
      undefined,
      { timeout: timeoutMs, maxTotalTimeout: timeoutMs },
    );
    const payload = decodeToolResult(name, response);
    const durationMs = Math.round(performance.now() - started);
    calls.push({ ...base, ok: true, duration_ms: durationMs });
    rawCalls.push({ ...base, response, duration_ms: durationMs });
    return payload;
  } catch (error) {
    calls.push({
      ...base,
      ok: false,
      duration_ms: Math.round(performance.now() - started),
      error_type: error?.name ?? "Error",
    });
    rawCalls.push(response === undefined
      ? { ...base, error_type: error?.name ?? "Error" }
      : { ...base, response, error_type: error?.name ?? "Error" });
    if (error instanceof ToolCallError) throw error;
    throw new ToolCallError(name, error?.message ?? String(error));
  }
}

export async function closeMcpProcess(client, transport, spawnImpl = spawn) {
  const ownedPid = transport?.pid ?? null;
  try {
    if (client) await client.close();
    else if (transport) await transport.close();
  } finally {
    // dnx is a wrapper on Windows. SDK close alone may leave its descendants alive.
    if (process.platform === "win32" && ownedPid) {
      await new Promise((resolve) => {
        const killer = spawnImpl("taskkill", ["/PID", String(ownedPid), "/T", "/F"], {
          windowsHide: true,
          stdio: "ignore",
        });
        killer.once("error", () => resolve());
        killer.once("close", () => resolve());
      });
    }
  }
}

/** Fixed serial sequence: load once, then definition + references for each symbol. */
export async function runDeterministicPlan(client, {
  solutionPath,
  fixtureRoot,
  symbols,
  timeoutMs = 120000,
}) {
  if (!Array.isArray(symbols) || symbols.length === 0) {
    throw new Error("At least one exact symbol is required");
  }
  for (const symbol of symbols) {
    if (!/^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$/.test(symbol)) {
      throw new Error(`Invalid exact symbol: ${symbol}`);
    }
  }
  const calls = [];
  const rawCalls = [];
  const callOptions = { timeoutMs, fixtureRoot, calls, rawCalls };
  try {
    await callSerial(client, "load_solution", { path: solutionPath, background: false }, callOptions);
    const results = [];
    for (const symbol of symbols) {
      const definitions = await callSerial(
        client, "go_to_definition", { symbol, limit: 50 }, callOptions,
      );
      const references = await callSerial(
        client, "find_references", { symbol, limit: 50 }, callOptions,
      );
      const definitionCount = resultTotal(definitions);
      results.push({
        symbol,
        status: definitionCount > 0 ? "found" : "not_found",
        definition_count: definitionCount,
        reference_count: resultTotal(references),
        definition_paths: publicPaths(definitions, fixtureRoot),
        reference_paths: publicPaths(references, fixtureRoot),
      });
    }
    return { results, calls, rawCalls };
  } catch (error) {
    error.calls = calls;
    error.rawCalls = rawCalls;
    throw error;
  }
}

function timestamp() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
}

function safeMessage(error, roots) {
  let text = error?.message ?? String(error);
  for (const root of roots) text = text.split(root).join("<LOCAL_PATH>");
  return text.slice(0, 500);
}

async function main() {
  const started = performance.now();
  const solutionArg = process.argv[2] ?? path.join(ROOT, "workspaces", "CleanArchitecture", "Clean.Architecture.slnx");
  const solutionPath = path.resolve(solutionArg);
  const fixtureRoot = path.dirname(solutionPath);
  const symbols = (process.argv[3] ?? "Contributor,BaseEntity")
    .split(",").map((value) => value.trim()).filter(Boolean);
  const timeoutMs = Number(process.env.MCP_TIMEOUT_MS ?? 120000);
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1000) throw new Error("MCP_TIMEOUT_MS must be >= 1000");
  if (![".sln", ".slnx"].includes(path.extname(solutionPath).toLowerCase()) || !fs.existsSync(solutionPath)) {
    throw new Error(`Exact solution path not found or not .sln/.slnx: ${solutionPath}`);
  }
  const runId = `deterministic-${timestamp()}`;
  const localDir = path.join(ROOT, "local-results", runId);
  const publicPath = path.join(ROOT, "results", "runs", `${runId}.json`);
  fs.mkdirSync(localDir, { recursive: true });
  fs.mkdirSync(path.dirname(publicPath), { recursive: true });
  const report = {
    schema_version: 1,
    utc: runId.replace("deterministic-", ""),
    method: "fixed_serial_controller_no_model",
    model_used: false,
    solution_name: path.basename(solutionPath),
    symbols,
    status: "starting",
    calls: [],
    results: [],
  };
  let transport;
  let client;
  const stderr = [];
  const captureStderr = (chunk) => {
    stderr.push(String(chunk));
    if (stderr.join("").length > 250000) stderr.splice(0, stderr.length - 1);
  };
  try {
    transport = new StdioClientTransport({
      command: "dnx",
      args: ["RoslynCodeLens.Mcp", "--yes"],
      cwd: fixtureRoot,
      stderr: "pipe",
    });
    transport.stderr.on("data", captureStderr);
    client = new Client({ name: "deterministic-orchestration", version: "1.0.0" }, { capabilities: {} });
    await client.connect(transport, { timeout: timeoutMs, maxTotalTimeout: timeoutMs });
    const catalog = await client.listTools({}, { timeout: timeoutMs, maxTotalTimeout: timeoutMs });
    const available = new Set(catalog.tools.map((tool) => tool.name));
    report.available_tool_count = available.size;
    report.server = client.getServerVersion();
    const missing = REQUIRED_TOOLS.filter((name) => !available.has(name));
    if (missing.length) throw new Error(`Required MCP tools missing: ${missing.join(", ")}`);
    const planned = await runDeterministicPlan(client, {
      solutionPath, fixtureRoot, symbols, timeoutMs,
    });
    report.calls = planned.calls;
    report.results = planned.results;
    fs.writeFileSync(path.join(localDir, "raw-calls.json"), JSON.stringify(planned.rawCalls, null, 2) + "\n");
    report.status = "complete";
  } catch (error) {
    report.status = "error";
    if (error.calls) report.calls = error.calls;
    if (error.rawCalls) {
      fs.writeFileSync(path.join(localDir, "raw-calls.json"), JSON.stringify(error.rawCalls, null, 2) + "\n");
    }
    report.error = {
      type: error?.name ?? "Error",
      tool: error?.tool ?? undefined,
      message: safeMessage(error, [ROOT, fixtureRoot, path.parse(ROOT).root]),
    };
  } finally {
    const runtime = { node_pid: process.pid, transport_pid: transport?.pid ?? null };
    fs.writeFileSync(path.join(localDir, "runtime.json"), JSON.stringify(runtime, null, 2) + "\n");
    try { await closeMcpProcess(client, transport); } catch { /* Close is followed by runner-owned tree cleanup. */ }
    report.duration_ms = Math.round(performance.now() - started);
    fs.writeFileSync(path.join(localDir, "server-stderr.log"), stderr.join(""));
    fs.writeFileSync(publicPath, JSON.stringify(report, null, 2) + "\n");
    console.log(`Deterministic report: ${path.relative(ROOT, publicPath)}`);
  }
  if (report.status !== "complete") throw new Error(report.error?.message ?? "Deterministic orchestration failed");
  for (const result of report.results) {
    console.log(`${result.symbol}: ${result.status}; definitions=${result.definition_count}; references=${result.reference_count}`);
  }
  console.log(`Controller called ${report.calls.length} fixed tools in ${report.duration_ms} ms; no model was used.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch((error) => {
    console.error(error?.message ?? String(error));
    process.exitCode = 1;
  });
}
