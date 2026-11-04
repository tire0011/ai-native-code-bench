"""Shared model requests and result handling; no third-party dependencies."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class Generation:
    text: str
    prompt_tokens: int
    completion_tokens: int
    duration_ns: int


def generate(*, endpoint: str, model: str, prompt: str, json_mode: bool = False) -> Generation:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "seed": 42},
    }
    if json_mode:
        payload["format"] = "json"
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=240) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(str(result["error"]))
    return Generation(
        text=result["response"],
        prompt_tokens=int(result.get("prompt_eval_count", 0)),
        completion_tokens=int(result.get("eval_count", 0)),
        duration_ns=int(result.get("total_duration", 0)),
    )


def python_source(response: str) -> str:
    """Extract the first fenced Python block, or use the full response."""
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", response, re.I | re.S)
    return (match.group(1) if match else response).strip() + "\n"


def json_object(response: str) -> dict:
    value = json.loads(response)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object containing the Edict module AST")
    return value


def visible_result(response: object) -> str:
    """Flatten MCP content for diagnostics, without hiding structured errors."""
    if isinstance(response, dict):
        content = response.get("content")
        if isinstance(content, list):
            return "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return json.dumps(response, ensure_ascii=False)

