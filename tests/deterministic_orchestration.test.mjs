import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { EventEmitter } from "node:events";
import {
  ToolCallError,
  closeMcpProcess,
  decodeToolResult,
  publicPaths,
  runDeterministicPlan,
} from "../deterministic_orchestration.mjs";

const fixtureRoot = path.resolve("fixture");
const solutionPath = path.join(fixtureRoot, "Example.slnx");

function ok(items, totalCount = items.length) {
  return {
    content: [{ type: "text", text: JSON.stringify({ items, totalCount }) }],
  };
}

test("fixed plan calls load once, then definition and references serially for each exact symbol", async () => {
  const invocations = [];
  let active = 0;
  const client = {
    async callTool(request, _schema, options) {
      assert.equal(options.timeout, 5000);
      assert.equal(options.maxTotalTimeout, 5000);
      active += 1;
      assert.equal(active, 1, "controller must never overlap MCP calls");
      await new Promise((resolve) => setImmediate(resolve));
      active -= 1;
      invocations.push(request);
      if (request.name === "load_solution") return ok([]);
      if (request.name === "go_to_definition") {
        return request.arguments.symbol === "Contributor"
          ? ok([{ file: path.join(fixtureRoot, "src/Core/Contributor.cs") }])
          : ok([]);
      }
      if (request.name === "find_references") {
        return request.arguments.symbol === "Contributor"
          ? ok([{ file: path.join(fixtureRoot, "src/UseCases/ContributorService.cs") }])
          : ok([]);
      }
      throw new Error(`Unexpected tool: ${request.name}`);
    },
  };
  const output = await runDeterministicPlan(client, {
    solutionPath,
    fixtureRoot,
    symbols: ["Contributor", "BaseEntity"],
    timeoutMs: 5000,
  });
  assert.deepEqual(invocations.map((call) => call.name), [
    "load_solution",
    "go_to_definition", "find_references",
    "go_to_definition", "find_references",
  ]);
  assert.equal(invocations[0].arguments.path, solutionPath);
  assert.equal(invocations[0].arguments.background, false);
  assert.deepEqual(output.results.map((result) => result.status), ["found", "not_found"]);
  assert.deepEqual(output.results[0].definition_paths, ["src/Core/Contributor.cs"]);
  assert.deepEqual(output.results[0].reference_paths, ["src/UseCases/ContributorService.cs"]);
  assert.equal(output.results[1].definition_count, 0);
  assert.equal(output.calls.length, 5);
  assert.equal(output.calls.filter((call) => call.arguments.path === "<solution>").length, 1);
});

test("a tool error stops the fixed plan immediately", async () => {
  let count = 0;
  const client = {
    async callTool() {
      count += 1;
      return { isError: true, content: [{ type: "text", text: "Solution not found" }] };
    },
  };
  await assert.rejects(
    runDeterministicPlan(client, { solutionPath, fixtureRoot, symbols: ["Contributor"] }),
    (error) => error instanceof ToolCallError && error.tool === "load_solution",
  );
  assert.equal(count, 1, "definition/reference calls must not follow a failed load");
});

test("plain-text status responses are retained and failed calls preserve evidence", async () => {
  assert.deepEqual(
    decodeToolResult("load_solution", { content: [{ type: "text", text: "Solution loaded" }] }),
    { text: "Solution loaded" },
  );
  const client = {
    async callTool() {
      return { isError: true, content: [{ type: "text", text: "bad solution" }] };
    },
  };
  await assert.rejects(
    runDeterministicPlan(client, { solutionPath, fixtureRoot, symbols: ["Contributor"] }),
    (error) => {
      assert.equal(error.calls.length, 1);
      assert.equal(error.calls[0].ok, false);
      assert.equal(error.rawCalls.length, 1);
      assert.equal(error.rawCalls[0].response.isError, true);
      return true;
    },
  );
});

test("SDK-level failure stops without pretending another tool succeeded", async () => {
  let count = 0;
  const client = {
    async callTool(request) {
      count += 1;
      if (request.name === "go_to_definition") throw new Error("compiler unavailable");
      return ok([]);
    },
  };
  await assert.rejects(
    runDeterministicPlan(client, { solutionPath, fixtureRoot, symbols: ["Contributor"] }),
    /go_to_definition: compiler unavailable/,
  );
  assert.equal(count, 2);
});

test("nested tool envelopes and public paths are bounded", () => {
  const payload = decodeToolResult("find_references", {
    content: [{
      type: "text",
      text: JSON.stringify({
        result: {
          totalCount: 75,
          items: Array.from({ length: 75 }, (_, index) => ({ file: `src/File${index}.cs` })),
        },
      }),
    }],
  });
  const files = publicPaths(payload, fixtureRoot);
  assert.equal(files.length, 50);
  assert.equal(files[0], "src/File0.cs");
});

test("external absolute paths never leak into the public paths", () => {
  const payload = decodeToolResult("go_to_definition", {
    structuredContent: {
      items: [{ file: path.resolve(fixtureRoot, "..", "outside", "Secret.cs") }],
      totalCount: 1,
    },
  });
  assert.deepEqual(publicPaths(payload, fixtureRoot), ["<external>"]);
});

test("Windows cleanup targets only the runner-owned MCP transport tree", { skip: process.platform !== "win32" }, async () => {
  const invocations = [];
  let clientClosed = false;
  const fakeSpawn = (command, args) => {
    invocations.push({ command, args });
    const child = new EventEmitter();
    setImmediate(() => child.emit("close", 0));
    return child;
  };
  await closeMcpProcess(
    { async close() { clientClosed = true; } },
    { pid: 12345 },
    fakeSpawn,
  );
  assert.equal(clientClosed, true);
  assert.deepEqual(invocations, [{
    command: "taskkill",
    args: ["/PID", "12345", "/T", "/F"],
  }]);
});

test("invalid symbol syntax fails before any tool can be selected", async () => {
  let count = 0;
  const client = { async callTool() { count += 1; return ok([]); } };
  await assert.rejects(
    runDeterministicPlan(client, { solutionPath, fixtureRoot, symbols: ["Contributor; rm *"] }),
    /Invalid exact symbol/,
  );
  assert.equal(count, 0);
});
