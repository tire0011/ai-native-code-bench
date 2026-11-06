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
