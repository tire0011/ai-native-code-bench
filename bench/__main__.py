"""CLI runner. This is a plumbing smoke test, not a research-grade benchmark."""

from __future__ import annotations

import argparse
import json
from time import perf_counter_ns
from datetime import datetime, timezone
from pathlib import Path

from .core import generate, json_object, python_source
from .edict import EdictSession, normalize_duplicate_ids
from .execution import run_python
from .prompting import COMPACT_GUIDE, PromptContext, official_context


EDICT_EXAMPLE = {"kind": "module", "id": "mod-hello-001", "name": "hello", "imports": [],
                 "definitions": [{"kind": "fn", "id": "fn-main-001", "name": "main", "params": [],
                 "effects": ["io"], "returnType": {"kind": "basic", "name": "Int"},
                 "contracts": [], "body": [{"kind": "call", "id": "call-print-001",
                 "fn": {"kind": "ident", "id": "ident-print-001", "name": "print"},
                 "args": [{"kind": "literal", "id": "lit-msg-001", "value": "Hello, World!"}]},
                 {"kind": "literal", "id": "lit-ret-001", "value": 0}]}]}


EDICT_RULES = (
    "Return ONLY a complete JSON object for an Edict module AST. "
    "Use a main function returning Int, with effect io. Print the computed result and return 0. "
    "All AST nodes with a 'kind' MUST have their own unique 'id' throughout the entire tree, "
    "including every occurrence of an ident node. Never reuse an id. "
    "Do not generate loops or declarations named while, for, variant, or assign: "
    "they are NOT Edict expression node kinds. "
    "For these small smoke tests, express the calculation as nested arithmetic "
    "using binop nodes with op, left, and right; literal nodes contain value. "
    "Allowed expression kinds are literal, ident, binop, unop, call, if, let, "
    "match, array, tuple_expr, record_expr, enum_constructor, access, lambda, "
    "block, string_interp, forall, exists, and tool_call. "
    "Prefer only literal, binop, ident, and call. Do not emit Python syntax."
)


def edict_prompt(task_prompt: str, variant: str = "baseline", context: str = "") -> str:
    arithmetic = {"kind": "binop", "id": "add-001", "op": "+",
                  "left": {"kind": "literal", "id": "num-001", "value": 2},
                  "right": {"kind": "literal", "id": "num-002", "value": 3}}
    base = (
        EDICT_RULES + "\nValid Edict module example:\n"
        + json.dumps(EDICT_EXAMPLE, separators=(",", ":"))
        + "\nValid arithmetic expression example (place inside call.args):\n"
        + json.dumps(arithmetic, separators=(",", ":"))
    )
    if variant == "baseline":
        return base + "\nTask: " + task_prompt
    if variant == "compact":
        return base + "\nCompact Edict authoring guide:\n" + COMPACT_GUIDE + "\nTask: " + task_prompt
    if variant == "official":
        if not context:
            raise ValueError("Official Edict prompting requires fetched MCP documentation")
        return base + "\nInstalled Edict documentation:\n" + context + "\nTask: " + task_prompt
    raise ValueError(f"Unknown Edict prompt variant: {variant}")


def edict_repair_prompt(task_prompt: str, previous_output: str, error: str,
                        variant: str = "baseline", context: str = "") -> str:
    guidance = ""
    if variant == "compact":
        guidance = "\nCompact Edict authoring guide:\n" + COMPACT_GUIDE
    elif variant == "official":
        guidance = "\nInstalled Edict documentation (excerpt):\n" + context
    elif variant != "baseline":
        raise ValueError(f"Unknown Edict prompt variant: {variant}")
    return (
        EDICT_RULES + "\nYour previous Edict AST failed the compiler. "
        "Repair it using the EXACT compiler diagnostic. Return the entire corrected module, "
        "not a patch or an explanation." + guidance + "\nTask: " + task_prompt
        + "\nPrevious AST:\n" + previous_output[:8000 if variant == "official" else 14000]
        + "\nCompiler errors:\n" + error[:3000 if variant == "official" else 6000]
    )


def run_edict(*, task: dict, endpoint: str, model: str, max_repairs: int,
              execute: bool, record: dict, prompt_variant: str = "baseline",
              prompt_context: str = "") -> None:
    """Attempt Edict compilation, optionally repairing from structured errors.

    Every model generation, even a failed one, is recorded and counted.
    """
    prompt = edict_prompt(task["prompt"], variant=prompt_variant, context=prompt_context)
    record["edict_prompt_variant"] = prompt_variant
    record["initial_prompt_chars"] = len(prompt)
    record["attempts"] = []
    record.update(prompt_tokens=0, completion_tokens=0, duration_ns=0)
    # Generation-only mode works without installing Edict on the host.
    if not execute:
        response = generate(endpoint=endpoint, model=model, prompt=prompt, json_mode=True)
        ast = json_object(response.text)
        record.update(artifact=ast, prompt_tokens=response.prompt_tokens,
                      completion_tokens=response.completion_tokens, duration_ns=response.duration_ns)
        return

    with EdictSession() as edict:
        for attempt_index in range(max_repairs + 1):
            response = generate(endpoint=endpoint, model=model, prompt=prompt, json_mode=True)
            attempt = {"index": attempt_index, "raw_response": response.text,
                       "input_prompt_chars": len(prompt),
                       "prompt_tokens": response.prompt_tokens,
                       "completion_tokens": response.completion_tokens,
                       "duration_ns": response.duration_ns}
            record["attempts"].append(attempt)
            record["prompt_tokens"] += response.prompt_tokens
            record["completion_tokens"] += response.completion_tokens
            record["duration_ns"] += response.duration_ns
            record["artifact"] = response.text
            try:
                ast = json_object(response.text)
                ast, changes = normalize_duplicate_ids(ast)
                attempt["normalized_ids"] = changes
                record["artifact"] = ast
                compiled = edict.compile(ast)
                record["compiled"] = True
                attempt["compiled"] = True
            except Exception as error:
                details = f"{type(error).__name__}: {error}"
                attempt["error"] = details
                if attempt_index == max_repairs:
                    record["error"] = details
                    record["failure_stage"] = "generation_or_compile"
                    return
                prompt = edict_repair_prompt(task["prompt"], response.text, details,
                                             variant=prompt_variant, context=prompt_context)
                continue

            # WASM instantiation/validation errors belong to the execution
            # stage. Do not ask the model to fix a compiler backend failure.
            try:
                record["stdout"] = edict.run(compiled)
                record["passed"] = record["stdout"] == task["expected_stdout"]
            except Exception as error:
                record["error"] = f"{type(error).__name__}: {error}"
                record["failure_stage"] = "wasm_execution"
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--mode", choices=("python", "edict", "both"), default="both")
    parser.add_argument("--tasks", type=Path, default=Path("tasks/smoke.json"))
    parser.add_argument("--output", type=Path, default=Path("results/smoke.jsonl"))
    parser.add_argument("--no-execute", action="store_true", help="Generate only; avoid running generated code")
    parser.add_argument("--max-edict-repairs", type=int, default=2,
                        help="Compiler-feedback repair attempts after initial Edict generation (default: 2)")
    parser.add_argument("--edict-prompt", choices=("baseline", "official", "compact", "all"),
                        default="baseline", help="Edict prompt profile, or all three for comparison")
    parser.add_argument("--edict-doc-chars", type=int, default=8000,
                        help="Maximum official schema/example excerpt length (default: 8000)")
    args = parser.parse_args()
    if args.max_edict_repairs < 0:
        parser.error("--max-edict-repairs must not be negative")
    if args.edict_doc_chars < 1000:
        parser.error("--edict-doc-chars must be at least 1000")

    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    modes = ("python", "edict") if args.mode == "both" else (args.mode,)
    prompt_variants = (("baseline", "official", "compact") if args.edict_prompt == "all"
                       else (args.edict_prompt,))
    cases = ([("python", "python")] if "python" in modes else [])
    cases += [("edict", variant) for variant in prompt_variants] if "edict" in modes else []
    documentation: PromptContext | None = None
    if "edict" in modes and "official" in prompt_variants:
        # The docs are frozen for this run and fetched only once, not per task.
        with EdictSession() as edict:
            documentation = official_context(edict, args.edict_doc_chars)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as output:
        for task in tasks:
            for mode, variant in cases:
                prompt = (
                    "Write a standalone Python 3.12 program solving this task. "
                    "Print exactly the required result, with no explanation. "
                    "Return source code only.\nTask: " + task["prompt"]
                )
                record = {"at": datetime.now(timezone.utc).isoformat(), "task": task["id"],
                          "mode": mode, "model": args.model, "expected_stdout": task["expected_stdout"]}
                if mode == "edict" and variant == "official" and documentation is not None:
                    record["official_documentation"] = {
                        "sha256": documentation.source_sha256,
                        "source_chars": documentation.source_chars,
                        "included_chars": documentation.included_chars,
                    }
                started_ns = perf_counter_ns()
                try:
                    if mode == "python":
                        response = generate(endpoint=args.endpoint, model=args.model,
                                            prompt=prompt, json_mode=False)
                        record.update(prompt_tokens=response.prompt_tokens,
                                      completion_tokens=response.completion_tokens,
                                      duration_ns=response.duration_ns)
                        code = python_source(response.text)
                        record["artifact"] = code
                        if not args.no_execute:
                            record["stdout"] = run_python(code)
                            record["passed"] = record["stdout"] == task["expected_stdout"]
                    else:
                        run_edict(task=task, endpoint=args.endpoint, model=args.model,
                                  max_repairs=args.max_edict_repairs,
                                  execute=not args.no_execute, record=record,
                                  prompt_variant=variant,
                                  prompt_context=documentation.text if variant == "official" and documentation else "")
                except Exception as error:
                    record["error"] = f"{type(error).__name__}: {error}"
                record["wall_duration_ns"] = perf_counter_ns() - started_ns
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                verdict = record.get("passed", "not scored")
                label = f"{mode}/{variant}" if mode == "edict" else mode
                print(f"{task['id']} / {label}: {verdict}" +
                      (f" — {record['error']}" if "error" in record else ""))
    print(f"Results: {args.output}")


if __name__ == "__main__":
    main()

