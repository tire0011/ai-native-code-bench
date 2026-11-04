"""Replay a recorded Edict AST without an LLM, then isolate WASM failures.

This is a compiler diagnostic, not a benchmark run: the modified variants do
not preserve the original program's behavior or expected output.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Iterator

from .edict import EdictSession, normalize_duplicate_ids


DEFAULT_FIXTURE = Path("fixtures/edict/even-sum-20-wasm-invalid.json")


def load_ast(path: Path, task: str | None = None) -> dict:
    """Read a standalone AST or the most recent compiled Edict JSONL result."""
    if path.suffix != ".jsonl":
        ast = json.loads(path.read_text(encoding="utf-8"))
    else:
        selected = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if (record.get("mode") == "edict" and record.get("compiled")
                    and (task is None or record.get("task") == task)):
                selected = record
        if selected is None:
            raise ValueError(f"No compiled Edict result for task {task!r} in {path}")
        ast = selected.get("artifact")
        if isinstance(ast, str):
            ast = json.loads(ast)
    if not isinstance(ast, dict) or ast.get("kind") != "module":
        raise ValueError("Expected a complete Edict module AST")
    return normalize_duplicate_ids(ast)[0]


def diagnostic_variants(ast: dict) -> Iterator[tuple[str, dict]]:
    """Isolate a faulty block vs. a string expression without modifying the AST."""
    yield "original", deepcopy(ast)

    body = ast["definitions"][0]["body"]
    if not any(node.get("kind") == "block" for node in body):
        raise ValueError("This diagnostic requires a top-level block in main")
    if not any(node.get("kind") == "call" and node.get("fn", {}).get("name") == "print"
               for node in body):
        raise ValueError("This diagnostic requires a top-level print call in main")

    for name, remove_block, replace_print in (
        ("no_string_expression", False, True),
        ("no_block", True, False),
        ("no_block_or_string", True, True),
    ):
        variant = deepcopy(ast)
        candidate_body = variant["definitions"][0]["body"]
        if remove_block:
            candidate_body[:] = [node for node in candidate_body if node.get("kind") != "block"]
        if replace_print:
            for node in candidate_body:
                if node.get("kind") == "call" and node.get("fn", {}).get("name") == "print":
                    node["args"] = [{"kind": "literal", "id": "diag-print-literal", "value": "probe"}]
        yield name, variant


def run_diagnostics(ast: dict, edict: EdictSession) -> list[dict]:
    results = []
    for name, candidate in diagnostic_variants(ast):
        record = {"variant": name}
        try:
            compiled = edict.compile(candidate)
        except Exception as error:
            record.update(stage="compile", error=f"{type(error).__name__}: {error}")
        else:
            try:
                record.update(stage="ok", stdout=edict.run(compiled))
            except Exception as error:
                record.update(stage="wasm_execution", error=f"{type(error).__name__}: {error}")
        results.append(record)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_FIXTURE,
                        help="Standalone AST JSON or results/smoke.jsonl (default: bundled reproduction)")
    parser.add_argument("--task", default=None, help="Task ID to select from JSONL")
    args = parser.parse_args()
    ast = load_ast(args.input, args.task)
    with EdictSession() as edict:
        for result in run_diagnostics(ast, edict):
            print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
