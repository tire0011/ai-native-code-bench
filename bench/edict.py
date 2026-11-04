"""Minimal synchronous MCP stdio client for Edict; uses the official tool schemas."""

from __future__ import annotations

import json
import shutil
import subprocess
from copy import deepcopy
from typing import Any

from .core import visible_result


def normalize_duplicate_ids(ast: dict) -> tuple[dict, list[dict[str, str]]]:
    """Repair non-semantic duplicate AST node IDs, keeping original output intact.

    IDs identify AST nodes for diagnostics and patches; distinct occurrences
    must not reuse them. Record every intervention for research accounting.
    """
    normalized = deepcopy(ast)
    reserved: set[str] = set()

    def reserve(value: Any) -> None:
        if isinstance(value, dict):
            if "kind" in value and isinstance(value.get("id"), str):
                reserved.add(value["id"])
            for child in value.values():
                reserve(child)
        elif isinstance(value, list):
            for child in value:
                reserve(child)

    reserve(normalized)
    seen: set[str] = set()
    changes: list[dict[str, str]] = []
    counter = 0

    def walk(value: Any, path: str) -> None:
        nonlocal counter
        if isinstance(value, dict):
            if "kind" in value and isinstance(value.get("id"), str):
                original = value["id"]
                if original in seen:
                    counter += 1
                    replacement = f"{original}-dedup-{counter}"
                    while replacement in reserved:
                        counter += 1
                        replacement = f"{original}-dedup-{counter}"
                    value["id"] = replacement
                    reserved.add(replacement)
                    changes.append({"path": path, "old_id": original, "new_id": replacement})
                seen.add(value["id"])
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(normalized, "$")
    return normalized, changes


def decode_tool_result(result: dict) -> Any:
    """Decode a structured MCP result, or its JSON text payload if provided."""
    if result.get("isError"):
        raise RuntimeError(visible_result(result))
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    text = visible_result(result).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"output": text}


def nested_value(value: Any, keys: tuple[str, ...]) -> Any | None:
    """Search for a specific result field, including standard MCP content lists."""
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                return value[key]
        for child in value.values():
            found = nested_value(child, keys)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = nested_value(child, keys)
            if found is not None:
                return found
    return None


class EdictSession:
    def __init__(self) -> None:
        npx = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx:
            raise RuntimeError("Node.js / npx not found. Run npm install first.")
        self.proc = subprocess.Popen(
            [npx, "--no-install", "edict-lang"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.next_id = 0
        self.request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "ai-native-code-bench", "version": "0.1.0"},
        })
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        listed = self.request("tools/list", {})
        self.tools = {t["name"]: t.get("inputSchema", {}) for t in listed.get("tools", [])}

    def _send(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict) -> dict:
        self.next_id += 1
        request_id = self.next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            try:
                reply = json.loads(line)
            except json.JSONDecodeError:
                continue
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                raise RuntimeError(str(reply["error"]))
            return reply.get("result", {})
        raise RuntimeError(f"Edict MCP process closed while handling {method}")

    def call(self, tool: str, arguments: dict) -> dict:
        if tool not in self.tools:
            raise RuntimeError(f"Edict tool {tool} not found; available: {list(self.tools)}")
        return self.request("tools/call", {"name": tool, "arguments": arguments})

    def arguments_for(self, tool: str, value: Any) -> dict:
        """Fill a single program/binary parameter based on the installed MCP schema.

        Fail explicitly on ambiguous schemas; never guess multiple values.
        """
        schema = self.tools[tool]
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        candidates = [key for key in ("ast", "program", "source", "wasm", "wasmBase64", "binary", "code") if key in properties]
        if len(required) == 1:
            key = required[0]
        elif len(candidates) == 1:
            key = candidates[0]
        else:
            raise RuntimeError(f"Unrecognized Edict {tool} input schema: {schema}")
        expected = properties.get(key, {}).get("type")
        if expected == "string" and not isinstance(value, str):
            value = json.dumps(value, separators=(",", ":"))
        return {key: value}

    def compile(self, ast: dict) -> dict:
        result = self.call("edict_compile", self.arguments_for("edict_compile", ast))
        decoded = decode_tool_result(result)
        if isinstance(decoded, dict) and decoded.get("ok") is False:
            raise RuntimeError(str(decoded)[:3000])
        return decoded

    def run(self, compiled: dict) -> str:
        wasm = nested_value(compiled, ("wasm", "wasmBase64", "wasm_base64", "base64"))
        if wasm is None:
            raise RuntimeError("No WASM binary found in Edict compiler response")
        result = decode_tool_result(self.call("edict_run", self.arguments_for("edict_run", wasm)))
        if isinstance(result, dict):
            if result.get("ok") is False or result.get("exitCode", 0) != 0:
                raise RuntimeError(str(result)[:3000])
            stdout = nested_value(result, ("stdout", "output"))
            if stdout is not None:
                return str(stdout).strip()
        raise RuntimeError(f"Unrecognized Edict runtime response: {result}")

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)

    def __enter__(self) -> "EdictSession":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

