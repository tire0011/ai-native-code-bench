"""Compare local Qwen answers with and without SCIP-derived snippets."""
import datetime as dt
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from runner import FIXTURE, ROOT, log
from scip_context import extract_symbol_context, occurrences

QUESTION = ("Find the file defining the C# type BaseEntity in ardalis/CleanArchitecture. "
            "Name the defining file and up to two files referencing it. "
            "Give repository-relative paths only; if uncertain say UNKNOWN.")


def compare(index_path, model="qwen2.5-coder:7b", timeout=150):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = {"schema_version": 1, "utc": stamp, "fixture": "ardalis/CleanArchitecture",
              "model": model, "method": "SCIP definition+references snippets", "cases": {}}
    output = ROOT / "results" / "runs" / f"context-compare-{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    local = ROOT / "local-results" / f"context-compare-{stamp}"
    local.mkdir(parents=True, exist_ok=True)
    try:
        snippet, matches, symbols = extract_symbol_context(index_path, FIXTURE)
        result["index"] = {"matched_occurrences": matches, "symbols": symbols, "context_chars": len(snippet)}
        if not matches or not snippet:
            result["status"] = "no_scip_symbols"
            return result
        all_hits = list(occurrences(index_path))
        selected = {sym for _, sym, _, defined in all_hits
                    if defined and sym.endswith(("BaseEntity#", "BaseEntity."))}
        definitions = {path.replace("\\", "/") for path, sym, _, defined in all_hits
                       if defined and sym in selected}
        references = {path.replace("\\", "/") for path, sym, _, defined in all_hits
                      if not defined and sym in selected}
        if not definitions:
            result["status"] = "no_scip_definitions"
            return result
        ollama = shutil.which("ollama")
        if not ollama:
            result["status"] = "ollama_not_in_path"
            return result
        for label, context in (("no_context", ""), ("scip_context", snippet)):
            prompt = (QUESTION + "\n" + ("Context from C# symbol index:\n" + context if context else
                      "No repository content is provided. Do not invent files."))
            started = time.monotonic()
            log(f"Qwen context comparison: {label}")
            try:
                process = subprocess.run([ollama, "run", model, prompt], cwd=FIXTURE,
                                         capture_output=True, text=True, encoding="utf-8",
                                         errors="replace", timeout=timeout)
                answer = process.stdout
                (local / f"{label}.txt").write_text(answer, encoding="utf-8")
                result["cases"][label] = {
                    "ok": process.returncode == 0,
                    "duration_s": round(time.monotonic() - started, 2),
                    "definition_path_found": any(path.lower() in answer.lower().replace("\\", "/")
                                                 for path in definitions),
                    "reference_paths_found": sum(path.lower() in answer.lower().replace("\\", "/")
                                                 for path in references),
                    "ground_truth_references": len(references)
                }
            except (OSError, subprocess.TimeoutExpired) as exc:
                result["cases"][label] = {"ok": False, "error": type(exc).__name__}
        result["status"] = "complete"
        return result
    except (ValueError, OSError) as exc:
        result["status"] = "index_read_error"
        result["error_type"] = type(exc).__name__
        return result
    finally:
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        log(f"Context comparison report: {output.relative_to(ROOT)}")
