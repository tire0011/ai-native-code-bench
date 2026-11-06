#!/usr/bin/env python3
"""Install and smoke-test existing code-context tools on a PUBLIC fixture only."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from runner import ROOT, FIXTURE, fixture, log

TOOLS = ROOT / ".tools"
AIDER_ENV = TOOLS / "aider-venv"
SCIP_TOOLS = TOOLS / "scip-dotnet"
MAX_LOG = 250000
# Automatic benchmark diagnostics are intentionally bounded.


def executable(directory, name):
    windows = os.name == "nt"
    return directory / ("Scripts" if windows else "bin") / (name + (".exe" if windows else ""))


def invoke_checked(args, cwd, timeout, label):
    log(label)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [str(x) for x in args], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "duration_s": round(time.monotonic()-started, 2),
        }, raw
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False, "exit_code": None,
            "duration_s": round(time.monotonic()-started, 2),
            "error": type(exc).__name__,
        }, str(exc)


def prepare_aider():
    python = executable(AIDER_ENV, "python")
    if not python.is_file():
        AIDER_ENV.parent.mkdir(parents=True, exist_ok=True)
        status, raw = invoke_checked(
            [sys.executable, "-m", "venv", AIDER_ENV], ROOT, 120,
            "Preparing isolated Aider Python environment..."
        )
        if not status["ok"]:
            return status, raw, None
    aider = executable(AIDER_ENV, "aider")
    if not aider.is_file():
        status, raw = invoke_checked(
            [python, "-m", "pip", "install", "--disable-pip-version-check", "aider-chat"],
            ROOT, 600, "Installing Aider into isolated environment (first run only)..."
        )
        if not status["ok"]:
            return status, raw, None
    return {"ok": True, "cached": True}, "", aider


def prepare_scip():
    exe = SCIP_TOOLS / ("scip-dotnet.exe" if os.name == "nt" else "scip-dotnet")
    if exe.is_file():
        return {"ok": True, "cached": True}, "", exe
    dotnet = shutil.which("dotnet")
    if not dotnet:
        return {"ok": False, "error": "dotnet_not_in_path"}, "", None
    SCIP_TOOLS.mkdir(parents=True, exist_ok=True)
    status, raw = invoke_checked(
        [dotnet, "tool", "install", "scip-dotnet", "--tool-path", SCIP_TOOLS],
        ROOT, 360, "Installing scip-dotnet into isolated tool directory (first run only)..."
    )
    if not status["ok"] or not exe.is_file():
        return status, raw, None
    return status, raw, exe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-tokens", type=int, default=2048)
    args = parser.parse_args()
    if args.map_tokens < 128 or args.map_tokens > 8192:
        parser.error("--map-tokens must be between 128 and 8192")
    solution, revision = fixture()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = {"schema_version": 1, "utc": stamp, "fixture": "ardalis/CleanArchitecture",
              "fixture_commit": revision, "tools": {}}
    logs = ROOT / "local-results" / ("context-" + stamp)
    logs.mkdir(parents=True, exist_ok=True)
    for name, prepare in (("aider", prepare_aider), ("scip", prepare_scip)):
        setup, setup_log, exe = prepare()
        (logs / (name + "-setup.log")).write_text(setup_log[-MAX_LOG:], encoding="utf-8")
        info = {"installation": setup}
        if exe is not None:
            if name == "aider":
                command = [exe, "--show-repo-map", "--map-tokens", str(args.map_tokens),
                           "--model", "ollama/qwen2.5-coder:7b",
                           "--no-auto-commits", "--yes", "--no-pretty"]
                status, raw = invoke_checked(command, FIXTURE, 240, "Generating Aider repository map...")
                (logs / "aider-map.txt").write_text(raw[:MAX_LOG], encoding="utf-8")
                info["generation"] = {**status, "characters": len(raw),
                                      "nonempty_lines": sum(bool(line.strip()) for line in raw.splitlines())}
            else:
                # The index is a binary SCIP artifact, kept locally only.
                index_path = FIXTURE / "index.scip"
                if index_path.exists():
                    index_path.unlink()
                status, raw = invoke_checked(
                    [exe, "index"], FIXTURE, 360, "Indexing public C# fixture via scip-dotnet..."
                )
                (logs / "scip-index.log").write_text(raw[:MAX_LOG], encoding="utf-8")
                info["generation"] = {**status, "index_created": index_path.is_file(),
                                      "index_bytes": index_path.stat().st_size if index_path.is_file() else 0}
        result["tools"][name] = info
        log(f"Context {name}: installed={setup.get('ok')}, generated={info.get('generation', {}).get('ok')}")
    out = ROOT / "results" / "runs" / ("context-" + stamp + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    log(f"Context comparison diagnostics: {out.relative_to(ROOT)}; detailed logs stay local")
    return 0


if __name__ == "__main__":
    sys.exit(main())
