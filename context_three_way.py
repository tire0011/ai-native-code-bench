"""Repeatable three-way local Qwen benchmark: no context, Aider map, SCIP snippets.

Only structured metrics are published. Raw prompts and model answers remain local.
"""
import datetime as dt
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from runner import FIXTURE, ROOT, log
from scip_context import extract_symbol_context, occurrences

MODEL = "qwen2.5-coder:7b"
TARGETS = ("Contributor", "ContributorStatus")
ARMS = ("no_context", "aider_map", "scip")
SEEDS = (42, 43)
MAX_CONTEXT = 8000
OPTIONS = {"temperature": 0, "num_ctx": 8192, "num_predict": 512}
PATH_PATTERN = re.compile(r"(?<![\w./-])(?:src|tests)/[\w./-]+\.cs\b", re.I)


def ground_truth(index, target):
    hits = list(occurrences(index))
    symbols = {sym for _, sym, _, definition in hits
               if definition and sym.endswith((target + "#", target + "."))}
    definitions = {p.replace("\\", "/") for p, sym, _, definition in hits
                   if definition and sym in symbols}
    references = {p.replace("\\", "/") for p, sym, _, definition in hits
                  if not definition and sym in symbols} - definitions
    return definitions, references


def score_answer(answer, definitions, references):
    paths = [p.replace("\\", "/") for p in PATH_PATTERN.findall(answer)]
    normalized = [p.lower() for p in paths]
    unique = set(normalized)
    correct_def = {p.lower() for p in definitions}
    correct_refs = {p.lower() for p in references}
    # Strict exact paths; extra or duplicate paths are penalized.
    true_refs = unique & correct_refs
    correct = unique & (correct_def | correct_refs)
    return {"definition_found": bool(unique & correct_def),
            "reference_paths_found": len(true_refs),
            "reference_paths_available": len(correct_refs),
            "output_paths": len(paths),
            "unexpected_paths": len(unique - (correct_def | correct_refs)),
            "duplicate_paths": len(paths) - len(unique),
            "format_valid": len(paths) <= 3 and len(paths) == len(unique),
            "exact_path_precision": round(len(correct) / len(unique), 3) if unique else 0.0}


def make_prompt(target, context):
    question = (f"Find the C# type {target} in ardalis/CleanArchitecture. "
                "Reply with the repository-relative path to ONE definition and up to TWO distinct "
                "files referencing that exact type. Only output paths, one per line, "
                "maximum three paths. If you cannot verify a path, output UNKNOWN.")
    return question + "\n\nReference data (may be empty):\n" + context


def generate(prompt, seed, timeout):
    payload = {"model": MODEL, "prompt": prompt, "stream": False,
               "options": {**OPTIONS, "seed": seed}}
    request = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    return data.get("response", ""), data.get("prompt_eval_count"), data.get("eval_count")


def compare_three_way(index, aider_map=None, timeout=150):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "results" / "runs" / f"context-three-way-{stamp}.json"
    local = ROOT / "local-results" / f"context-three-way-{stamp}"
    out.parent.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    map_text = (Path(aider_map).read_text(encoding="utf-8", errors="replace")
                if aider_map and Path(aider_map).is_file() else "")
    # Keep the original map in local-results; do not publish map or model responses.
    map_text = re.sub(r"\x1b\[[0-9;]*m", "", map_text)[:MAX_CONTEXT]
    report = {"schema_version": 1, "utc": stamp, "fixture": "ardalis/CleanArchitecture",
              "model": MODEL, "tasks": list(TARGETS), "arms": list(ARMS),
              "seeds": list(SEEDS), "options": OPTIONS,
              "context_limit_chars": MAX_CONTEXT,
              "aider_map_available": bool(map_text.strip()), "results": [],
              "status": "running"}
    try:
        for target in TARGETS:
            definitions, references = ground_truth(index, target)
            snippet, matches, symbols = extract_symbol_context(
                index, FIXTURE, target=target, limit=MAX_CONTEXT)
            if not definitions or not snippet:
                report["results"].append({"target": target, "status": "no_scip_ground_truth",
                                          "matches": matches, "symbols": symbols})
                continue
            for seed in SEEDS:
                for arm in ARMS:
                    if arm == "aider_map" and not map_text.strip():
                        report["results"].append({"target": target, "seed": seed, "arm": arm,
                                                  "status": "aider_map_missing"})
                        continue
                    context = {"no_context": "", "aider_map": map_text,
                               "scip": snippet}[arm]
                    prompt = make_prompt(target, context)
                    started = time.monotonic()
                    log(f"Three-way context: {target} {arm} seed={seed}")
                    row = {"target": target, "seed": seed, "arm": arm,
                           "context_chars": len(context), "scip_matches": matches}
                    try:
                        answer, prompt_tokens, output_tokens = generate(prompt, seed, timeout)
                        (local / f"{target}-{arm}-{seed}.txt").write_text(
                            answer, encoding="utf-8")
                        row.update({"status": "ok",
                                    "duration_s": round(time.monotonic() - started, 2),
                                    "prompt_tokens": prompt_tokens,
                                    "output_tokens": output_tokens,
                                    **score_answer(answer, definitions, references)})
                    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as exc:
                        row.update({"status": "error", "error_type": type(exc).__name__})
                    report["results"].append(row)
        complete = sum(r.get("status") == "ok" for r in report["results"])
        report["status"] = "complete" if complete == len(TARGETS) * len(ARMS) * len(SEEDS) else "partial"
        return report
    finally:
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        log(f"Three-way context metrics: {out.relative_to(ROOT)}")
