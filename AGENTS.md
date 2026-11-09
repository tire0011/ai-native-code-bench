# AI-Native Code Bench contributor guide

## Purpose and scope

This repository has two related but separate workflows:

1. **Local C# assistant:** `local.ps1` starts OpenCode with a local Ollama model, Roslyn MCP, bounded context, and local-only provider rules. This is interactive and does not upload code or results.
2. **Public benchmarking:** the Python scripts and PowerShell watcher compare models/context strategies on `ardalis/CleanArchitecture`, record real tool/build/test evidence, and may publish sanitized results.

Do not point the benchmark watcher or its public result logging at private/corporate source. The target fixture lives in ignored `workspaces/CleanArchitecture`. Start with `HANDOFF.md` for current verified state, known failures and prioritized open experiments, then read `README.md`, `RESEARCH.md`, the relevant latest `results/runs/*.json`, and GitHub Issue #2 before changing an experiment. A model response or successful process exit is not evidence that a tool ran or code is correct.

## Common commands

Run from the repository root in PowerShell:

```powershell
# If node_modules/ is missing, restore pinned local dependencies once.
npm ci

# Offline unit/regression suite; run after every relevant change.
python -m unittest discover -s tests -v

# Offline deterministic MCP controller tests.
npm run test:mcp

# Real serial load/definition/reference run without any model.
node deterministic_orchestration.mjs

# Validate PowerShell syntax without starting the UI.
$errors = $null; $tokens = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path 'local.ps1'), [ref]$tokens, [ref]$errors)

# Prepare the practical assistant and exercise its local OpenCode path.
.\local.ps1 -SetupOnly -SmokeTest

# Start the assistant on the public C# fixture.
.\local.ps1

# Compare real OpenCode tool calls for one already-installed local model.
python -u runner.py --model ollama/qwen3:8b --cases builtin-read --timeout 240

# Normal public benchmark, without upload or watcher.
.\run.ps1 -NoWatch -NoPush
```

`coding_bench.py`, `coding_repair.py`, and especially `multi_bench.py` are expensive opt-in experiments. They are not part of routine unit testing. Do not start them automatically. Check active Ollama work before starting another model; this 8 GiB GPU should run one coding model and one inference stream at a time.

## Repository map

| Path | Role |
| --- | --- |
| `HANDOFF.md` | Current evidence/model coverage, known failures, prioritized ideas, safety constraints and document map for a new agent |
| `local.ps1`, `assistant/` | Practical local assistant setup, generated OpenCode template, and C# working instructions |
| `runner.py`, `cases.json` | OpenCode tool-call runner and controlled read-only cases |
| `deterministic_orchestration.mjs`, `tests/deterministic_orchestration.test.mjs` | Fixed serial MCP controller and offline tests; no LLM or OpenCode agent loop |
| `package.json`, `package-lock.json` | Pinned official MCP JS SDK and `npm run test:mcp` entrypoint; Node 18+ |
| `context_probe.py`, `scip_context.py` | Local SCIP/Aider setup and semantic context selection |
| `context_compare.py`, `context_three_way.py` | Controlled model/context comparisons |
| `coding_*.py`, `multi_*.py` | Opt-in code-edit and repair experiments with real .NET validation |
| `run.ps1`, `watch*.ps1`, `sync-results.ps1` | Public benchmark orchestration, watcher, and result-only upload |
| `opencode.jsonc` | Benchmark-repository Roslyn MCP configuration; the local assistant generates its own target config |
| `tests/` | Standard-library Python `unittest` regression tests |
| `results/runs/`, `results/logs/` | Public structured metrics and bounded, best-effort sanitized diagnostics |
| `local-results/` | Ignored raw prompts, answers, logs, model profile, and experiment workspaces |
| `.tools/`, `workspaces/` | Ignored project-local tool environments and fixture checkouts |

## Change guidelines

- Keep changes focused on one measurable bottleneck. Follow the existing Python/ PowerShell style and avoid introducing another agent framework.
- Python automation uses the standard library unless an existing isolated tool environment already supplies a dependency. Install third-party tools only under ignored `.tools/`; never globally for this project.
- Deterministic MCP orchestration uses the pinned official JavaScript SDK in `package-lock.json`; tests use Node's built-in `node:test`. Keep tool plans serial, allowlisted and independent of model output.
- Use UTF-8 for child-process input/output on Windows. Do not mutate caller-owned environment dictionaries.
- Preserve raw diagnostics in ignored `local-results/`. Publish only structured metrics or the existing bounded/redacted logs, and never treat redaction as a privacy guarantee.
- Test semantic failure states (`no_scip_symbols`, timeouts, missing tools, partial results), not only successful exits. Never invent model scores when context selection failed.
- The generated OpenCode target file is `.opencode/opencode.jsonc`. Only overwrite it when it contains the `local.ps1` generated marker. Preserve all unrelated user configuration.
- Do not overwrite pre-existing result files or untracked user work. Do not perform Git mutations unless the user explicitly requests them; the existing watcher scripts are the exception only when the user deliberately runs their documented upload workflow.
- Update this file and relevant documentation when commands, structure, or workflows change.

## Acceptance checks for local-assistant changes

1. Run all Python unit tests, `npm run test:mcp`, and PowerShell parser validation.
2. Run `.\local.ps1 -SetupOnly -SmokeTest` against the public fixture. When changing deterministic orchestration, also run `node deterministic_orchestration.mjs`; do not use a model for this integration check.
3. Confirm `ollama ps` reports the intended context and inspect `PROCESSOR`; `100% GPU` is the performance target, not something to claim without evidence.
4. Verify that OpenCode discovers `ollama/csharp-local` and Roslyn connects, or inspect a deterministic report for successful fixed MCP calls and stopped runner-owned processes.
5. For tool/model changes, use `runner.py` and inspect real JSON events. The `probe` agent hard-denies edits, shell, Code Mode execution, web tools, and subagents; keep those read-only safeguards. Windows timeouts terminate the process tree. Printed tool-call JSON inside text is a failure, not a tool invocation; `required_tools_succeeded`, failed tool metadata, and timeouts matter more than exit code 0.
6. For coding changes, inspect the final diff and require real `dotnet build`/`dotnet test` evidence before calling the task successful.
