# Local Coding Context Benchmark

Test how well small local models interact with **Roslyn MCP** through **OpenCode v2** on an independent public C# codebase. No corporate source code is needed.

## One-time setup (Windows / PowerShell)

Requirements: Git, Python 3.11+, OpenCode v2, .NET 10 SDK (required by Roslyn CodeLens MCP), and a configured local model. The repository contains its own **project-local** `opencode.jsonc`; it does not overwrite your global providers or models.

```powershell
 git clone https://github.com/tire0011/ai-native-code-bench.git
 Set-Location ai-native-code-bench
 .\run.ps1 -Model 'ollama/qwen2.5-coder:7b'
```

Replace the model ID with the exact ID shown by `opencode models`. To compare a second model, run `./run.ps1 -Model 'YOUR_PROVIDER/YOUR_MODEL'` in a fresh invocation. The script automatically clones [ardalis/CleanArchitecture](https://github.com/ardalis/CleanArchitecture) into ignored `workspaces/` and discovers its `.sln` or `.slnx`.

## Submit results

```powershell
 git add results/runs
 git commit -m 'Add local context benchmark results'
 git push
```

Run artifacts with complete raw model responses and tool payloads are retained under **ignored** `local-results/`, never staged automatically. Published JSON contains only timing, model ID, tool names and counts, basic completion status, and the public fixture commit SHA. Review before pushing. A model that merely prints JSON tool-call text is **not** counted as actually invoking a tool.

## What is measured

Three independently executed prompts: MCP discovery/solution loading, class-symbol lookup, and reference discovery. A tool invocation is counted only when an OpenCode JSON event records a tool call; response text is not a tool call. Roslyn-specific calls are distinguished from other OpenCode tools. This first milestone assesses **tool execution reliability**, not code-change correctness or semantic understanding.

```powershell
 python -m unittest discover -s tests -v
 .\run.ps1 -Model 'ollama/qwen2.5-coder:7b' -Cases 'load,find-symbol'
```

### Notes

* Roslyn CodeLens has shown slow startup when automatically loading large solutions. The MCP starts in this benchmark's root directory, **not** in the fixture; each prompt asks for an explicit background solution load.
* The runner records the fixture Git SHA to make comparisons reproducible. It does not automatically reset an existing fixture clone; remove `workspaces/CleanArchitecture` to re-clone the current upstream version.
* Models/providers may differ in their tool support. If a tool does not exist in the catalog, record the failure instead of inventing a call.
* No automatic code execution/build/fixes yet. OpenCode runs in read-oriented `plan` mode. The benchmark does not attempt to upload workspace files.
* Do not run the benchmark from a private source directory; do not publish raw logs or local model credentials.
