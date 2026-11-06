# Local Coding Context Benchmark

Reproducible tests of **local Qwen + OpenCode v2 + Roslyn MCP** on a public C# project ([ardalis/CleanArchitecture](https://github.com/ardalis/CleanArchitecture)). No company code required.

## Windows / PowerShell

Prerequisites: Git, Python 3.11+, OpenCode v2, .NET 10 SDK, and a local Ollama Qwen model configured in OpenCode.

One-time checkout:

```powershell
git clone https://github.com/tire0011/ai-native-code-bench.git
Set-Location ai-native-code-bench
```

Every run:

```powershell
git pull
.\run.ps1
```

**That's it.** The default model is always `ollama/qwen2.5-coder:7b`. The script runs local unit tests, prepares the public C# project, executes three OpenCode/Roslyn cases, prints progress and the actual tool names, creates a compact summary, then automatically runs **git add, commit and push on main** for `results/runs` only. Even failing experiments generate and upload diagnostic summaries if they reach the runner.

Use `.\run.ps1 -NoPush` for an offline dry run. For future model comparisons you can explicitly override `-Model`, but no argument is required for Qwen. Set `-TimeoutSeconds 600` if a case genuinely takes longer.

Raw responses and tool payloads are stored in ignored `local-results/` **only on your PC**. Public JSON summaries contain status, timing, model name, tool names/counts and the fixture commit, not the code or transcripts. Review before uploading if you change the experiment to target private code.

## What the benchmark actually measures

- Whether OpenCode executes actual Roslyn MCP calls, rather than Qwen merely printing tool-call-looking JSON.
- Whether the public solution can be loaded and its symbols/references queried.
- Per-case elapsed time, exit code, timeouts, and errors.

This **does not yet measure coding correctness**, and even a successful tool call does not prove the answer is correct. We will add validated code-understanding cases next.

The Roslyn MCP is declared in the project-local `opencode.jsonc`; global providers remain unchanged. Large solutions should be loaded explicitly in the background rather than automatically during server initialization.

If `opencode` launches in PowerShell but Python cannot find it, check `Get-Command opencode | Select-Object Source` and `where.exe opencode`. This runner uses the resolved executable path on Windows to avoid `WinError 2`.

This project is experimental. Results depend on local OpenCode, Ollama, Roslyn and .NET installations.


## Automatic runs when the repository changes

Install or update the scheduled task on your Windows PC (PowerShell, while signed in):

```powershell
git pull
.\install-watcher.ps1
```

Windows Task Scheduler launches a two-check cycle every minute (30 seconds apart) to check `origin/main` **about every 30 seconds**. If benchmark code, configuration or test cases changed, it fast-forwards the local checkout and automatically starts `run.ps1` with local Qwen, including the normal results-only commit/push. If only files inside `results/runs/` changed, it pulls but does **not** rerun (prevents feedback loops). Uncommitted tracked changes or diverged branches are never overwritten. The watcher does not start concurrent runs.

Logs remain on your PC: `local-results/watch.log` (watch status) and `local-results/watch-run-*.log` (test output). The task runs in your signed-in Windows session, so the PC must be on, your user must be logged in, and Ollama/OpenCode must be available.

Manual single check: `.watch.ps1`. Remove the task with:

```powershell
Unregister-ScheduledTask -TaskName 'AI Native Code Bench Watcher' -Confirm:$false
```

## Public diagnostic logs

Each run now uploads bounded, best-effort redacted OpenCode output to `results/logs/<run-id>/<case>.log` alongside `results/runs`. Full unmodified logs stay in ignored `local-results/`. Because this is a **public GitHub repository**, never change the fixture to corporate/private code or include secrets in prompts. Automated redaction is not a security guarantee. Results and logs are pushed by `run.ps1` automatically; no manual upload required.

## Tool-calling control experiment

The first case, `builtin-read`, asks Qwen to invoke OpenCode's built-in `read` tool on the public fixture's README. It does not require the Roslyn MCP. If this case has zero actual tool events, diagnose local model/tool-call integration before changing Roslyn. Subsequent cases target Roslyn. The number of actual tool events (not JSON printed as text) is recorded in the result JSON.

## Automatic Aider / SCIP context baselines

`run.ps1` also runs `context_probe.py`. On first use it **installs tools automatically and locally**, never into global Python/.NET locations:

- Aider: `.tools/aider-venv/` (isolated Python virtual environment, `aider-chat`).
- scip-dotnet: `.tools/scip-dotnet/` (local `dotnet tool install --tool-path`).

Subsequent runs reuse installed tools. Aider's documented `--show-repo-map` creates a map for the public CleanArchitecture fixture; scip-dotnet runs `index` to generate a local binary `index.scip`. Only timing, status, size and fixture revision are uploaded in `results/runs/context-*.json`; detailed output and binary artifacts stay in ignored local folders. Failed setup is reported per tool and does not prevent OpenCode tests from completing. These are **baseline smoke tests**, not yet comparative Qwen code-quality scores. Installation requires internet access and a compatible Python/.NET runtime; the script records errors if unavailable. The benchmark never installs to corporate repositories.

To run only the two context probes manually (PowerShell):
```powershell
python -u context_probe.py
```
