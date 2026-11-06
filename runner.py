#!/usr/bin/env python3
"""Run local OpenCode/Roslyn experiments against a public C# repository."""
import argparse
import datetime as dt
import json
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "workspaces" / "CleanArchitecture"
MODEL = "ollama/qwen2.5-coder:7b"

def log(msg):
    print(f"[{dt.datetime.now().astimezone():%H:%M:%S}] {msg}", flush=True)

def run(cmd, **kw):
    return subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", **kw)

def fixture():
    if not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        log("Cloning public C# fixture...")
        run(["git", "clone", "--depth", "1",
             "https://github.com/ardalis/CleanArchitecture.git", str(FIXTURE)], check=True)
    rev = run(["git", "-C", str(FIXTURE), "rev-parse", "HEAD"],
              capture_output=True, check=True).stdout.strip()
    slns = sorted((*FIXTURE.rglob("*.sln"), *FIXTURE.rglob("*.slnx")),
                  key=lambda p: (len(p.parts), str(p)))
    if not slns:
        raise RuntimeError("No .sln/.slnx in public fixture")
    return str(slns[0].resolve()), rev

def parse_event(line):
    try:
        value = json.loads(line)
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None

def tool_name(event):
    if not event or event.get("type") not in ("tool_use", "tool-call", "tool_call"):
        return None
    part = event.get("part") or event.get("data") or {}
    if not isinstance(part, dict):
        return None
    name = part.get("tool") or part.get("name") or event.get("tool")
    return name if isinstance(name, str) and re.fullmatch(r"[\w.:-]{1,120}", name) else None

def parse_events(raw):
    counts, events, errors = {}, 0, 0
    for line in raw.splitlines():
        evt = parse_event(line)
        if evt is None:
            continue
        events += 1
        name = tool_name(evt)
        if name:
            counts[name] = counts.get(name, 0) + 1
        if evt.get("type") in ("error", "tool_error"):
            errors += 1
    return {"events": events, "tool_calls": counts,
            "tool_calls_total": sum(counts.values()),
            "roslyn_calls": sum(v for k, v in counts.items() if "roslyn" in k.lower()),
            "error_events": errors}

def invoke(cmd, target, timeout):
    """Stream command output to local ignored log, emit progress without raw content."""
    messages = queue.Queue()
    try:
        process = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace", bufsize=1)
    except OSError as exc:
        log(f"OpenCode could not start: {exc}")
        target.write_text(f"START ERROR: {exc}\n", encoding="utf-8")
        return "", None, False, type(exc).__name__

    def reader():
        try:
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)
    threading.Thread(target=reader, daemon=True).start()
    started, last = time.monotonic(), time.monotonic()
    lines, timed_out, done = [], False, False
    with target.open("w", encoding="utf-8") as output:
        while not done:
            now = time.monotonic()
            if now - started >= timeout:
                log(f"Timeout after {timeout}s; stopping OpenCode")
                process.kill()
                timed_out = True
                break
            try:
                line = messages.get(timeout=1)
            except queue.Empty:
                if now - last >= 15:
                    log(f"... working for {int(now-started)}s")
                    last = now
                continue
            if line is None:
                done = True
                break
            lines.append(line)
            output.write(line)
            output.flush()
            evt = parse_event(line)
            name = tool_name(evt)
            if name:
                log(f"TOOL {name}")
                last = time.monotonic()
            elif evt and evt.get("type") in ("error", "tool_error"):
                log("ERROR event (details in local-results)")
                last = time.monotonic()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        while not messages.empty():
            line = messages.get_nowait()
            if line is not None:
                lines.append(line)
                output.write(line)
    return "".join(lines), process.returncode, timed_out, None

def sanitize_public_log(raw):
    """Best-effort removal of common secrets and machine-specific paths.

    Published logs remain PUBLIC. Use only with the public benchmark fixture.
    """
    import os
    text = raw
    for value in [str(ROOT), str(FIXTURE), str(Path.home())]:
        if value:
            text = re.sub(re.escape(value), "<LOCAL_PATH>", text, flags=re.I)
    # Strip common credential-bearing headers, environment assignments and JWTs.
    text = re.sub(r'(?i)(Authorization\s*[:=]\s*Bearer\s+)[^\s"\\]+',
                  r'\1<REDACTED>', text)
    text = re.sub(r'(?i)(["\']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)["\']?\s*[:=]\s*["\']?)[^\s"\'\\,}]+',
                  r'\1<REDACTED>', text)
    text = re.sub(r'\beyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b',
                  '<REDACTED_JWT>', text)
    return text[:250000] + ("\n[TRUNCATED]\n" if len(text) > 250000 else "")


def build_opencode_command(model, prompt):
    return ["run", "--standalone", "--agent", "build",
            "--format", "json", "--model", model, prompt]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--cases", default="")
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()
    if args.timeout < 10:
        parser.error("timeout must be >= 10 seconds")
    if not shutil.which("git"):
        parser.error("git missing")
    solution, revision = fixture()
    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    selected = set(filter(None, (s.strip() for s in args.cases.split(","))))
    if selected:
        missing = selected - {case["id"] for case in cases}
        if missing:
            parser.error(f"Unknown cases: {sorted(missing)}")
        cases = [case for case in cases if case["id"] in selected]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_model = re.sub(r"[^A-Za-z0-9_-]", "_", args.model)[:65]
    run_id = f"{stamp}-{safe_model}"
    local = ROOT / "local-results" / run_id
    published = ROOT / "results" / "runs"
    local.mkdir(parents=True, exist_ok=True)
    published.mkdir(parents=True, exist_ok=True)
    public_logs = ROOT / "results" / "logs" / run_id
    public_logs.mkdir(parents=True, exist_ok=True)
    log(f"Model: {args.model}; fixture commit: {revision[:12]}")
    results = []
    for i, case in enumerate(cases, 1):
        log(f"[{i}/{len(cases)}] Running {case['id']}")
        prompt = ("READ-ONLY research on a PUBLIC C# repo. Do not access other "
                  "repos, credentials or configs. Never modify files. "
                  f"Solution: {solution}. " + case["goal"])
        command = build_opencode_command(args.model, prompt)
        start = time.monotonic()
        exe = shutil.which("opencode")
        if exe:
            raw, code, timeout, error = invoke([exe, *command],
                                                local / (case["id"] + ".jsonl"), args.timeout)
        else:
            raw, code, timeout, error = "", None, False, "opencode_not_in_PATH"
            log("OpenCode missing from PATH")
        # Keep full output locally; publish a bounded, best-effort redacted copy.
        # Never publish other sources than the controlled public fixture.
        (public_logs / (case["id"] + ".log")).write_text(
            sanitize_public_log(raw), encoding="utf-8")
        metrics = parse_events(raw)
        results.append({"case": case["id"], "model": args.model,
                        "duration_s": round(time.monotonic()-start, 2),
                        "exit_code": code, "timeout": timeout, "start_error": error,
                        "tool_invoked": metrics["tool_calls_total"] > 0,
                        "roslyn_invoked": metrics["roslyn_calls"] > 0, **metrics})
        log(f"Finished {case['id']}: exit={code}, tools={metrics['tool_calls_total']}, "
            f"roslyn={metrics['roslyn_calls']}, errors={metrics['error_events']}")
    report = {"schema_version": 2, "utc": stamp,
              "fixture": "ardalis/CleanArchitecture", "fixture_commit": revision,
              "solution_name": Path(solution).name, "results": results}
    path = published / f"{run_id}.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log(f"Summary: {path.relative_to(ROOT)}; public logs: {public_logs.relative_to(ROOT)}; full local log: {local.relative_to(ROOT)}")
    return 0 if all(r["exit_code"] == 0 and not r["timeout"] for r in results) else 1

if __name__ == "__main__":
    sys.exit(main())
