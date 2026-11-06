# AI-Native Code Bench

**Can a small, locally running coding LLM become a useful C# development assistant if deterministic tools prepare the right code context for it?**

This repository is an **experimental benchmark and automation harness**, not a production coding agent or a new foundation model. It compares alternative ways of understanding a C# codebase while keeping inference local, reproducible and measurable.

> **For AI assistants opening this repository:** Read this README, then [Issue #2](https://github.com/tire0011/ai-native-code-bench/issues/2), before proposing changes. **Do not assume that successful process exit means a tool was called or that an answer is correct.** Prefer fixing the current experiment and analyzing existing results over introducing another agent framework.

## 1. Research question and hypothesis

A large coding assistant can inspect a repository through tools. Small models can struggle to invoke tools reliably or locate relevant code in a large solution. Our working hypothesis is that a **smaller local model + a reliable external C# symbol/context engine** may solve useful coding tasks at lower inference cost.

The experiments compare:

| Approach | What it does | Current role |
| --- | --- | --- |
| OpenCode v2 + Ollama Qwen2.5-Coder:7B | Model attempts real built-in and Roslyn MCP tool calls | Tool-calling baseline |
| scip-dotnet + small model | .NET semantic index selects definitions/references and supplies bounded source excerpts as prompt context | Main context-engineering experiment |
| Aider repository map + small model | Repo-map representation supplies structural context | Planned comparison baseline |
| Other local models, e.g. Ornith + Serena | Alternative model and agent/tool integration | Future experiment, **not yet benchmarked here** |

The goal is **correct C# changes that pass builds and tests**, not simply generating plausible answers. Current experiments only test tool use and file/symbol identification; code-edit quality tests are a future milestone.

## 2. Data flow

```text
GitHub main (benchmark scripts, tests, test triggers)
         |
         v
Windows PowerShell watcher (polls origin/main, ~30 seconds)
         |
         | only reruns for non-result changes
         v
run.ps1
   |-- Python unit tests
   |-- runner.py --------------> OpenCode v2 -> Ollama Qwen 7B
   |                                   | built-in read / Roslyn MCP requests
   |
   |-- context_probe.py
   |     |-- Aider installation and repo-map probe
   |     |-- scip-dotnet index -> index.scip (local only)
   |     '-- context_compare.py -> SCIP snippets -> Ollama Qwen 7B
   |                                   | same question without/with context
   v
results/runs/*.json + results/logs/**  (public, bounded diagnostics)
         |
         '-- git commit + push to main
               |
               '-- GitHub tracker Issue #2 / assistant analysis
```

**Execution modes:** The Windows machine performs local inference and indexing. GitHub stores the code and selected diagnostic results. A remote web assistant uses GitHub and the watcher: it can edit GitHub files and inspect published results but **cannot directly execute the local Windows benchmark**. Our watcher must be active for automatic runs. The local Codex desktop assistant can execute experiments directly; the watcher is currently paused during direct research.

## 3. The safe public fixture

All experiments target the public repository **[ardalis/CleanArchitecture](https://github.com/ardalis/CleanArchitecture)**. `runner.py` clones it on first use to `workspaces/CleanArchitecture`; this checkout is gitignored. It uses its `.slnx` and source files to test symbol lookup.

**Do not point these scripts at corporate/private repositories.** `results/logs/` contains best-effort redacted outputs, which are still public; redaction is not a security guarantee. Complete raw outputs and model answers stay in ignored `local-results/`. Generated tools, SCIP index and other binary artifacts must stay local, not be committed.

## 4. Run on Windows (PowerShell only)

Prerequisites: Git, Python, .NET SDK, OpenCode v2, Ollama with `qwen2.5-coder:7b` downloaded and available. Aider, uv and scip-dotnet are installed **by the project scripts** in ignored `.tools/` directories as needed; no global installation of those dependencies is intended.

```powershell
git clone https://github.com/tire0011/ai-native-code-bench.git
Set-Location ai-native-code-bench
.\run.ps1
```

A manual `run.ps1` executes the benchmark, attempts to upload its results, **then enters the foreground watcher** in the same PowerShell console. Stop watching with **Ctrl+C**.

Useful variations:

```powershell
.\run.ps1 -NoWatch            # one benchmark, no monitoring afterward
.\run.ps1 -NoWatch -NoPush    # local results only; do not upload
.\watch-loop.ps1             # start watcher directly (no immediate benchmark)
python -u context_probe.py   # context tooling only; does not upload by itself
```

With an existing checkout, use `git pull` first when the watcher is not running. The watcher normally fetches and fast-forwards automatically. It must not overwrite uncommitted tracked changes or force-push. Commits containing only `results/runs/` and `results/logs/` do **not** start another benchmark.

**Only one monitoring mechanism should run at a time.** The normal workflow is `watch-loop.ps1` in a visible PowerShell window. An older Task Scheduler mechanism (`install-watcher.ps1`) also exists; do not activate both.

### Files you should know

| File/path | Purpose |
| --- | --- |
| `run.ps1` | Entry point, unit tests, experiments, safe results-only Git push, then optional watcher |
| `watch-loop.ps1`, `watch.ps1` | Foreground polling and guarded synchronization; internal runs use `-NoWatch` |
| `runner.py`, `cases.json` | OpenCode tool-calling cases and structured event metrics |
| `opencode.jsonc` | Project-local Roslyn MCP configuration |
| `context_probe.py` | Installs Aider/scip-dotnet locally, creates repo map / SCIP index, launches context comparison |
| `scip_context.py` | Reads SCIP protobuf occurrences, resolves symbols and prepares bounded C# snippets |
| `context_compare.py` | Prompts Qwen with and without SCIP-selected context and scores file paths |
| `tests/` | Python regression tests (including synthetic SCIP data) |
| `results/runs/` | Public machine-readable benchmark summaries |
| `results/logs/` | Public bounded, best-effort sanitized OpenCode diagnostics |
| `local-results/`, `.tools/`, `workspaces/` | Local-only logs, tools and fixture; ignored by Git |
| `benchmark-trigger.json` | Lightweight committed change that can trigger a rerun |
| [Issue #2](https://github.com/tire0011/ai-native-code-bench/issues/2) | Living experiment tracker, blockers, hypotheses and next steps |

## 5. Current verified results and blockers (2026-11-06)

**Verified by uploaded results:**
- Local watcher can upload benchmark results to GitHub.
- `scip-dotnet` successfully indexes the public C# fixture and creates a **446,292-byte** `index.scip`. Recorded generation time varies by run.
- In OpenCode Qwen2.5-Coder:7B has produced **zero genuine tool events** in the tested built-in `read` and Roslyn cases. Some responses merely print tool-call-looking JSON; that is not an actual invocation.
- The initial context experiment targeting `BaseEntity` returned **zero matching SCIP symbols**, so **no valid Qwen with/without context comparison has been measured yet**.
- Aider installation has failed with **exit code 2**; the root cause is not yet confirmed.

**Changes awaiting confirmation from a new local run:**
- The symbol target was changed to a class defined in the fixture, `Contributor`; additional SCIP diagnostics were added to reveal document/definition counts.
- Aider installer now reports a bounded set of sanitized error hints and installation stage.

Do not mark these changes as successful until a new result file demonstrates that they work. Check the latest `results/runs/context-*.json` and `context-compare-*.json`, and correlate them with the commit being tested.

## 6. Evaluation rules

1. Compare *the same task* with identical model, fixture revision and controlled prompt/context budget.
2. Score ground-truth paths, symbols and later **build/test outcomes**; do not equate exit code 0 with semantic success.
3. Record durations, errors, index generation time and reproducible environment details.
4. If the context selector returns zero symbols, report `no_scip_symbols` (or equivalent); **never invent a model score**.
5. Fix one measurable bottleneck at a time, add a regression test, let the watcher run, then evaluate the uploaded result.
6. Keep all corporate source code, credentials and full prompts out of the public repository and result logs.

## 7. How another assistant should continue

1. Read **[Issue #2](https://github.com/tire0011/ai-native-code-bench/issues/2)** and inspect the newest results before implementing anything.
2. Check whether there is an uploaded run **after the most recent relevant code commit**. If there is no newer run, distinguish an inactive watcher from a long-running benchmark or a failed push; do not claim the change was tested.
3. If SCIP has zero matches, inspect the index parser and bounded symbol diagnostics; avoid assuming the fixture defines an external library type.
4. If Aider installation fails, use the reported stage/error hints to make a focused fix rather than retrying blindly.
5. Change scripts and tests through GitHub; local watcher should pull, execute, upload result files, and return to polling.
6. Update Issue #2 with **observed results**, commit references, remaining blockers and next actions.

**The intended end state:** a reproducible comparison showing whether deterministic C# context retrieval lets a compact local model solve real development tasks with reliable correctness and acceptable speed/cost.

## Direct local research (2026-11-06)

Aider has been installed successfully in `.tools/aider-py312-venv` using managed Python 3.12.16. UTF-8 child output is required on Windows. A single-method Qwen pilot passed 21 real C# tests; this is not yet evidence for large changes. `multi_bench.py` now compares baseline/map-disabled, Aider repository map and SCIP-selected context on a multi-file feature using the same local model/editor, isolated checkouts and compiler/test feedback. Results are in `results/runs/multi-*.json`; see `RESEARCH.md` for scope and limitations. No large-change success has been confirmed yet.

Local polling can be paused with the file `local-results/watcher.paused`. The foreground loop exits on its next iteration; individual watcher checks return without pulling or starting benchmarks. Remove the file to enable polling again. Direct Python experiments are unaffected.

## Direct local code-edit experiment

`python -u coding_bench.py` runs a bounded three-condition Qwen experiment on an isolated copy of the public fixture, using real .NET project tests. It does not push results or start a watcher. `python -u coding_repair.py <coding-run-id>` performs one additional repair using compiler feedback and installed dependency API documentation. See RESEARCH.md for prerequisites, the first 21/21-test success and limitations. Prompts and generated code stay under ignored local-results/; compact result metrics go to results/runs/.


## Bounded multi-file repair experiments

`multi_bench.py` is a **separate, opt-in, expensive** local coding benchmark; it is NOT automatically invoked by `run.ps1` or the 30-second watcher. The previous open-ended repair loop was changed to stop after **four new rounds per invocation** (override with `MULTI_MAX_NEW_ROUNDS`) or after **three non-improving rounds per arm** (override with `MULTI_STALE_LIMIT`). The last report then states `needs_review` rather than implying completion. Candidate edits are evaluated against real .NET tests; `best-production.zip` retains the best-scoring code state, and failed regressions are restored.

For the foreground watcher, a stale `local-results/watcher.paused` marker from Codex Desktop is automatically cleared when launching `watch-loop.ps1` explicitly; existing installations need to pull the updated script once first. The watcher still avoids repeating tests for commits containing only result/log files.

Do not assume an increasing number of model calls indicates meaningful progress. Change the failure-specific context or task decomposition before resuming a stalled arm.


### Concurrent GitHub updates and automatic result upload

The watcher and `run.ps1` now share `sync-results.ps1`. It commits only benchmark result/log files, fetches origin/main, rebases **only local result-only commits**, and retries pushes up to four times if another GitHub client pushed meanwhile. It refuses to rebase local code commits or overwrite tracked non-result changes; no force-push. If a previous run left uncommitted result files, the watcher synchronizes those safely before pulling. A genuine local code modification still requires user review.

The currently running older watcher script must be restarted after updating the repository. `git status --short` identifies any local files preventing the first pull.

## Controlled three-way Qwen context comparison

The normal watcher-triggered `run.ps1` now runs `context_probe.py`, which generates a fresh SCIP index and an Aider repository map (when Aider is available). Then `context_three_way.py` asks **the same repository-symbol lookup question** under three conditions: no context, up to 8,000 characters of Aider map, or up to 8,000 characters of SCIP-selected definition/reference snippets. Two symbols (`Contributor`, `ContributorStatus`) and two fixed seeds (42, 43) yield up to **12 model responses**. Ollama runs the same Qwen2.5-Coder:7B, temperature 0, context 8192 and generation limit 512 for all arms.

Metrics are published as `results/runs/context-three-way-*.json`. Scoring checks exact repository-relative paths, duplicates, unexpected paths, output format, durations and Ollama token counts. **No model answers or map text are published.** The baseline has less prompt context by design; context byte counts and prompt tokens are recorded, so this is a context-availability comparison, **not an equal-token ablation**. Two symbols and two seeds are an initial smoke test, not a statistically robust general ranking. If Aider is unavailable the arm is explicitly marked missing, never replaced by fabricated data.

This is a **read-only symbol lookup experiment**. The separate `multi_bench.py` C# code-edit test remains explicitly opt-in and is never launched by the watcher.

## Hardware telemetry and alternative model test

`resource_monitor.py` samples **Windows system-wide CPU utilization, used system RAM, NVIDIA GPU utilization and GPU memory** every 3 seconds when running the context probes. Each experiment publishes only average/peak statistics in `resources` fields; values are `null` when not supported or NVIDIA tools are absent. These are **system-level** readings, not per-model/per-process resource attribution. OpenCode's old `runner.py` tests have no resource attribution yet.

The Aider repository-map smoke test uses `--no-browser --no-show-model-warnings --no-detect-urls` to avoid unrelated documentation windows from a non-interactive benchmark. Model-metadata warnings are not proof of a broken model; see [Aider model warnings](https://aider.chat/docs/llms/warnings.html).

To test another already-installed local model without changing the default baseline:

```powershell
$env:CONTEXT_MODEL = 'qwen3:8b'
python -u context_probe.py
Remove-Item Env:CONTEXT_MODEL
```

This standalone command **does not upload** results automatically. To compare and upload using the normal watcher, keep Qwen2.5-Coder:7B as baseline and explicitly configure `CONTEXT_MODEL` in the watcher process before starting; avoid changing models mid-comparison. The `qwen3:8b` Ollama model is about 5.2 GB compared with ~4.7 GB for `qwen2.5-coder:7b`, and may compete for the same 8 GB VRAM with context/KV cache. Do not assume the newer model is faster or more accurate before measuring it.
