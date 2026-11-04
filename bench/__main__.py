"""CLI runner. This is a plumbing smoke test, not a research-grade benchmark."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .core import generate, json_object, python_source
from .edict import EdictSession
from .execution import run_python


EDICT_EXAMPLE = {"kind": "module", "id": "mod-hello-001", "name": "hello", "imports": [],
                 "definitions": [{"kind": "fn", "id": "fn-main-001", "name": "main", "params": [],
                 "effects": ["io"], "returnType": {"kind": "basic", "name": "Int"},
                 "contracts": [], "body": [{"kind": "call", "id": "call-print-001",
                 "fn": {"kind": "ident", "id": "ident-print-001", "name": "print"},
                 "args": [{"kind": "literal", "id": "lit-msg-001", "value": "Hello, World!"}]},
                 {"kind": "literal", "id": "lit-ret-001", "value": 0}]}]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--mode", choices=("python", "edict", "both"), default="both")
    parser.add_argument("--tasks", type=Path, default=Path("tasks/smoke.json"))
    parser.add_argument("--output", type=Path, default=Path("results/smoke.jsonl"))
    parser.add_argument("--no-execute", action="store_true", help="Generate only; avoid running generated code")
    args = parser.parse_args()

    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    modes = ("python", "edict") if args.mode == "both" else (args.mode,)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as output:
        for task in tasks:
            for mode in modes:
                prompt = (
                    "Write a standalone Python 3.12 program solving this task. "
                    "Print exactly the required result, with no explanation. "
                    "Return source code only.\nTask: " + task["prompt"]
                ) if mode == "python" else (
                    "Return ONLY one JSON object representing a complete Edict module AST. "
                    "Create a main() function returning Int, using print for output. "
                    "Use unique node IDs. Here is a valid Hello World Edict AST example:\n"
                    + json.dumps(EDICT_EXAMPLE, separators=(",", ":"))
                    + "\nTask: " + task["prompt"]
                )
                record = {"at": datetime.now(timezone.utc).isoformat(), "task": task["id"],
                          "mode": mode, "model": args.model, "expected_stdout": task["expected_stdout"]}
                try:
                    response = generate(endpoint=args.endpoint, model=args.model,
                                        prompt=prompt, json_mode=(mode == "edict"))
                    record.update(prompt_tokens=response.prompt_tokens,
                                  completion_tokens=response.completion_tokens,
                                  duration_ns=response.duration_ns)
                    if mode == "python":
                        code = python_source(response.text)
                        record["artifact"] = code
                        if not args.no_execute:
                            record["stdout"] = run_python(code)
                            record["passed"] = record["stdout"] == task["expected_stdout"]
                    else:
                        ast = json_object(response.text)
                        record["artifact"] = ast
                        if not args.no_execute:
                            with EdictSession() as edict:
                                compiled = edict.compile(ast)
                                record["compiled"] = True
                                record["stdout"] = edict.run(compiled)
                                record["passed"] = record["stdout"] == task["expected_stdout"]
                except Exception as error:
                    record["error"] = f"{type(error).__name__}: {error}"
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                verdict = record.get("passed", "not scored")
                print(f"{task['id']} / {mode}: {verdict}" +
                      (f" — {record['error']}" if "error" in record else ""))
    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()

