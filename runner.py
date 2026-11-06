#!/usr/bin/env python3
"""Isolated OpenCode/Roslyn tool-call smoke benchmark for a PUBLIC C# repository."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "workspaces" / "CleanArchitecture"
UPSTREAM = "https://github.com/ardalis/CleanArchitecture.git"


def run(command, **kwargs):
    return subprocess.run(command, text=True, encoding="utf-8", errors="replace", **kwargs)


def checkout_fixture():
    if not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        print("Cloning public fixture (first run only)...", flush=True)
        p = run(["git", "clone", "--depth", "1", UPSTREAM, str(FIXTURE)])
        if p.returncode: raise RuntimeError("Public fixture clone failed")
    rev = run(["git", "-C", str(FIXTURE), "rev-parse", "HEAD"], capture_output=True, check=True).stdout.strip()
    slns = sorted((*FIXTURE.rglob("*.sln"), *FIXTURE.rglob("*.slnx")), key=lambda p: (len(p.parts), str(p)))
    if not slns: raise RuntimeError("No .sln or .slnx in public fixture")
    return str(slns[0].resolve()), rev


def parse_events(raw):
    counts = {}
    total_events = 0
    response_chars = 0
    for line in raw.splitlines():
        try: event = json.loads(line)
        except (ValueError, TypeError): continue
        if not isinstance(event, dict): continue
        total_events += 1
        event_type = str(event.get("type", ""))
        part = event.get("part") or event.get("data") or {}
        if not isinstance(part, dict): part = {}
        # OpenCode JSON event: {type:'tool_use',part:{tool:'...',state:{...}}}
        if event_type in ("tool_use", "tool-call", "tool_call"):
            tool = part.get("tool") or part.get("name") or event.get("tool")
            if isinstance(tool, str) and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,120}", tool):
                counts[tool] = counts.get(tool, 0) + 1
        if event_type == "text":
            response_chars += len(str(part.get("text", "")))
    return {"events": total_events, "tool_calls": counts,
            "tool_calls_total": sum(counts.values()),
            "roslyn_calls": sum(v for k, v in counts.items() if "roslyn" in k.lower()),
            "response_chars": response_chars}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--cases", default="")
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()
    if not shutil.which("opencode"): parser.error("opencode not found in PATH")
    if not shutil.which("git"): parser.error("git not found in PATH")
    if args.timeout < 10: parser.error("timeout must be >= 10 seconds")
    solution, revision = checkout_fixture()
    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    chosen = set(filter(None, (x.strip() for x in args.cases.split(","))))
    if chosen:
        unknown = chosen - {c["id"] for c in cases}
        if unknown: parser.error(f"Unknown case(s): {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in chosen]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model = re.sub(r"[^A-Za-z0-9_-]", "_", args.model)[:65]
    run_id = f"{stamp}-{safe_model}"
    raw_dir = ROOT / "local-results" / run_id
    pub_dir = ROOT / "results" / "runs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pub_dir.mkdir(parents=True, exist_ok=True)
    records = []
    print(f"Public fixture: {revision[:12]} | Solution: {Path(solution).name}")
    for case in cases:
        print(f"Running {case['id']} with {args.model} ...", flush=True)
        prompt = ("You are conducting a READ-ONLY test against a PUBLIC C# repository. "
                  "Do not touch other repos, local configurations, environment variables, "
                  "credentials, or services. Only investigate the supplied PUBLIC solution. "
                  f"Solution path: {solution}. " + case["goal"])
        command = ["opencode", "run", "--standalone", "--archived", "--agent", "plan",
                   "--format", "json", "--model", args.model, prompt]
        start = time.monotonic()
        try:
            proc = run(command, cwd=ROOT, capture_output=True, timeout=args.timeout)
            stdout, stderr, exit_code, timed_out = proc.stdout, proc.stderr, proc.returncode, False
        except subprocess.TimeoutExpired as exc:
            def decode(x): return x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")
            stdout, stderr, exit_code, timed_out = decode(exc.stdout), decode(exc.stderr), None, True
        elapsed = round(time.monotonic() - start, 2)
        (raw_dir / (case["id"] + ".jsonl")).write_text(stdout, encoding="utf-8")
        (raw_dir / (case["id"] + ".stderr.txt")).write_text(stderr, encoding="utf-8")
        stats = parse_events(stdout)
        record = {"case": case["id"], "model": args.model, "duration_s": elapsed,
                  "exit_code": exit_code, "timeout": timed_out,
                  "tool_invoked": stats["tool_calls_total"] > 0,
                  "roslyn_invoked": stats["roslyn_calls"] > 0, **stats}
        records.append(record)
        print(f"  tools={stats['tool_calls_total']}, roslyn={stats['roslyn_calls']}, "
              f"time={elapsed}s, exit={exit_code}, timeout={timed_out}", flush=True)
    report = {"schema_version": 1, "utc": stamp, "fixture": "ardalis/CleanArchitecture",
              "fixture_commit": revision, "solution_name": Path(solution).name,
              "opencode_cli": "v2", "results": records}
    destination = pub_dir / (run_id + ".json")
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Published summary: {destination.relative_to(ROOT)}")
    print(f"Ignored local raw logs: {raw_dir.relative_to(ROOT)}")
    print("Review the JSON, then: git add results/runs; git commit -m 'Add benchmark run'; git push")
    return 0 if all(r["exit_code"] == 0 and not r["timeout"] for r in records) else 1

if __name__ == "__main__":
    sys.exit(main())
