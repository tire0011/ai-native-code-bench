# Local C# Assistant — Agent Handoff

**Status:** 2026-11-09. Read this file first, then `AGENTS.md` for engineering conventions and `RESEARCH.md` for the chronological evidence.

This is a research repository, not a finished autonomous C# programmer. Its strongest current result is a **deterministic Roslyn MCP controller that performs definition/reference navigation without any LLM**. The local OpenCode/Ollama launcher also works, but model-driven tool use is not reliable enough to trust.

## 1. Goal and hard constraints

Goal: make a small local LLM useful on a much larger C# codebase by preparing deterministic semantic context and verifying real changes with builds/tests.

- Machine: NVIDIA RTX 2000 Ada Laptop GPU, **8 GiB VRAM**, **32 GiB RAM**; i7-13850HX.
- Local runtime: Ollama + OpenCode + RoslynCodeLens.MCP. Local models tested: `qwen2.5-coder:7b` and `qwen3:8b`.
- Target public fixture only: `ardalis/CleanArchitecture` in ignored `workspaces/CleanArchitecture`, revision `da5491f1641f3d388e6cfc2c0ddd29f763746762`.
- Never point the public result logger/watcher at corporate/private source.
- Do not assume exit code 0, a fluent response, or a `tool_use` event proves task success. Inspect tool status, returned content, final diff, and actual builds/tests.
- Preserve existing uncommitted user work. Recent development was deliberately not committed or pushed; `git status`/`git diff` contain important working state that is not visible from `origin/main` alone.

## 2. What works — verified

### A. Local interactive infrastructure

`local.ps1` prepares `ollama/csharp-local` and an OpenCode C# profile without starting the watcher or uploading the target repository.

- Default base: `qwen3:8b` (5.2 GB download); alternative installed base: `qwen2.5-coder:7b`.
- The alias shares model blobs; it does not duplicate weights.
- Defaults: 8,192 context tokens, temperature 0.1, 4,096 predicted-token limit.
- Verified on this machine: **6.2 GB model allocation, 100% GPU, context 8192**.
- `LOCAL_OK` smoke test passes. This proves inference/config wiring only, not coding ability.
- Generated provider policy permits Ollama only; web tools are denied; helper agents use the same local model.
- Roslyn is exposed directly (`codemode=false`) with a 15-tool core allowlist rather than all 67 executable tools. The allowlist is a safety/core boundary, **not a proven token reduction**.
- Existing non-generated `.opencode/opencode.jsonc` is never overwritten.
- An already-running Ollama server keeps its original process environment; launcher-started servers additionally request q8_0 KV cache, flash attention, one model and one inference stream.

See `assistant/README.md`, `assistant/csharp.md`, and `assistant/MODELS.md`.

### B. Deterministic Roslyn navigation — strongest result

`deterministic_orchestration.mjs` uses official `@modelcontextprotocol/sdk` **1.32.2** directly. No LLM or OpenCode agent loop decides which tool runs.

Plan: `load_solution` once → `go_to_definition` + `find_references` serially for each exact symbol → stop immediately on failure.

Real result: **`results/runs/deterministic-20261109T154631Z.json`**

- `status=complete`, `model_used=false`, RoslynCodeLens 2.18.2.
- All **9 projects** loaded in 16.44 s.
- `Contributor`: **1 definition**, **37 reference occurrences** (not 37 unique files).
- Definition: `src/Clean.Architecture.Core/ContributorAggregate/Contributor.cs`.
- `BaseEntity`: real calls returned 0 definitions/references; reported `not_found` without fabrication.
- Five fixed calls completed in **23.898 s** total.
- Runner-owned MCP transport stopped; older independent OpenCode service was left alone.
- Raw responses: ignored `local-results/deterministic-20261109T154631Z/`.
- Public paths are bounded and repository-relative; reference paths repeat per occurrence.

This proves deterministic C# navigation. It does **not** prove natural-language planning, editing, compilation, test repair, or completion of a large feature.

### C. Older bounded code-edit result

Earlier `qwen2.5-coder:7b` work produced one focused method repair that passed **21/21 tests** after manually selected type/API context and compiler feedback. See `results/runs/coding-20261106T152454Z-repair.json` and `RESEARCH.md`.

This was a single supervised adaptive repair, not autonomous large-feature success and not a general model ranking.

### D. Tests and safety controls

Verified current suites:

- **29 Python tests** via `python -m unittest discover -s tests -v`.
- **8 Node MCP controller tests** via `npm run test:mcp`.
- PowerShell parser validation for `local.ps1` passes.
- Git diff checks report no whitespace errors (line-ending notices may appear on Windows).

The OpenCode benchmark now uses an eight-step `probe` agent that hard-denies edits, shell, Code Mode execution, subagents, and web tools. Windows timeouts terminate the runner-owned process tree. Tool-state errors, nested `execute` metadata failures, and required successful tool names are recorded.

## 3. What failed or remains unproven

### Qwen/OpenCode tool behavior

- Earlier Qwen2.5-Coder OpenCode runs had **no genuine built-in or Roslyn tool events**.
- Qwen3 made real built-in `read` calls and occasional real Roslyn calls, but was inconsistent.
- Observed failures: delegating instead of using Roslyn; guessing `.sln` when `.slnx` was supplied; stopping after listing a solution; invented JavaScript/`require()` calls; claiming tools were unavailable despite 67 connected; timeouts and irrelevant shell commands.
- One Qwen3 run successfully called `roslyn_load_solution` but also attempted unrelated commands including `dotnet workload install csharp`, then timed out. **No workload was installed.** This demonstrates why prompt-only read-only instructions are insufficient.
- A medium `reasoning_effort` experiment did not establish an overall improvement and was removed from the final profile.
- The last restricted synchronous-load probe produced zero tools and failed cleanly. See `results/runs/20261109T141917Z-ollama_csharp-local.json`.

**Do not claim Qwen3 completed autonomous definition/reference navigation.** The successful definition/reference result came from the separate no-model deterministic controller.

### Model coverage not yet tested

- **No 14B model is installed or measured here** (`qwen3:14b`, `qwen2.5-coder:14b`).
- No 30B+ model was tested. These are not the daily target on 8 GiB VRAM / 32 GiB RAM.
- A larger model is not presumed to solve tool orchestration. Any comparison must measure correctness, offload,RAM, latency, and builds/tests rather than model labels or vendor scores.

### Large-repository and coding limits

- No reliable autonomous large C# feature or multi-file change has been demonstrated.
- The previous multi-file experiment did not produce a clean successful autonomous arm.
- The deterministic controller needs **exact symbol names**; it does not yet turn an arbitrary feature request into a validated plan.
- Current deterministic integration uses synchronous loading. Large solutions may need longer `MCP_TIMEOUT_MS` and a measured background-load/per-project strategy.
- SCIP tooling currently creates a full index. Its parser reads the index into memory and has a 100 MB guard; there is no verified incremental solution for very large repositories.
- 8K model context cannot contain a large repository. Retrieval and bounded source selection are mandatory.

Older reports predate some metric fixes and can undercount nested/tool-state errors. Read raw logs where accuracy matters; do not compare old `error_events` blindly with newer corrected metrics.

## 4. Prioritized open experiments

Only change one measurable stage at a time.

### 1. Deterministic evidence → bounded read-only model response (next)

Supply already verified MCP definition/reference evidence to a local model **without tools**. Ask for file-cited answers. Keep MCP data as truth, preserve raw evidence locally, and score:

- expected definition path;
- cited files must exist in retrieved evidence;
- unexpected or invented paths;
- correct missing-symbol (`UNKNOWN`/`not_found`) behavior;
- latency, prompt/output tokens, GPU/CPU offload.

First compare Qwen3 8B and Qwen2.5-Coder 7B on identical evidence and generation settings. Do not start with 14B.

### 2. Small isolated edit with deterministic source retrieval

Extend the controller to fetch only a known method/type and relevant dependency APIs (e.g. fixed `get_method_source`/`get_overloads` calls), then let the model propose a bounded edit in an isolated public fixture copy.

Require a negative control, final diff, real `dotnet build`, and real project tests. Preserve existing behavior and do not modify tests merely to obtain a pass.

### 3. Deterministic compiler/test repair loop

Controller, not model:

1. Run allowlisted build/test commands.
2. Extract current diagnostics.
3. Resolve only implicated symbols/source/API documentation with fixed MCP calls.
4. Feed bounded evidence to the model.
5. Keep/revert candidates based on build/test score and stop after a small round/stagnation cap.

No model-selected shell command or package/system installation. Never call the workload installer as part of C# work.

### 4. Optional model-size comparison

Only after the same bounded 7B/8B evaluation exists, compare `qwen3:14b` (about 9 GB) and possibly Qwen2.5-Coder 14B. Expect partial CPU offload on 8 GiB VRAM. Record `ollama ps`, RAM, speed, correctness, and whether extra quality justifies the cost.

### 5. Scalability work, when justified by a real larger solution

- Measured background loading and per-project subsets.
- Cache deterministic MCP/SCIP results by solution/git revision.
- Exact-symbol/file retrieval before optional embeddings; do not add another agent framework by default.
- Token-budgeted type/method context instead of entire files/maps.
- Natural-language task decomposition must produce validated exact symbols/files; deterministic outcomes must remain independently checkable.

## 5. Commands

Run from repository root in PowerShell:

```powershell
# If node_modules/ is missing, install pinned project-local dependencies once:
npm ci

# Offline regression suites
python -m unittest discover -s tests -v
npm run test:mcp

# Strongest real integration baseline; no model
node deterministic_orchestration.mjs

# Explicit solution and exact symbols
node deterministic_orchestration.mjs `
  "workspaces/CleanArchitecture/Clean.Architecture.slnx" `
  "Contributor,BaseEntity"

# Larger load timeout only when justified
$env:MCP_TIMEOUT_MS = '600000'
node deterministic_orchestration.mjs
Remove-Item Env:MCP_TIMEOUT_MS

# Interactive local assistant setup and smoke test
.\local.ps1 -SetupOnly -SmokeTest

# Interactive session (experimental, not autonomous proof)
.\local.ps1

# Alternative already-installed model
.\local.ps1 -BaseModel qwen2.5-coder:7b

# Public benchmark without upload/watcher; still runs model experiments
.\run.ps1 -NoWatch -NoPush
```

Do not run normal `run.ps1` unaware of its default result-upload/watch behavior. `coding_bench.py`, `coding_repair.py`, and especially `multi_bench.py` are expensive, opt-in experiments, not routine tests.

## 6. Contributor safety and repository state

- Read `AGENTS.md` before editing. Update it, this handoff, and relevant documentation when behavior/workflows/current results change.
- Preserve raw full prompts/responses in ignored `local-results/`; publish only compact sanitized metrics.
- Check tool content and status, not merely presence of a tool event or successful CLI exit.
- Keep tool plans serial, allowlisted and independently verifiable. Do not invent a new framework unless a measured failure requires it.
- Do not terminate unrelated OpenCode/Roslyn services. Kill only a runner-owned process tree and verify ownership first.
- Do not overwrite user configs or unrelated `.gitignore` changes. The fixture has a pre-existing Aider-related `.gitignore` delta plus generated `.opencode/` and `index.scip` state.
- Install nothing globally. Use existing local Ollama model store, pinned npm dependencies or ignored `.tools/` environments only as documented.
- Do not commit/push unless the user explicitly asks. Never perform Git cleanup/rebase/reset just to make an experiment look clean.
- Reports and `RESEARCH.md` must distinguish observed evidence from proposals and must say when something was not tested or failed.

## 7. Document map

- `AGENTS.md`: coding conventions, repository map, test/acceptance rules.
- `README.md`: public project overview, safe fixture rules, local launcher introduction.
- `RESEARCH.md`: chronological measurements, failed attempts, and interpretations.
- `assistant/README.md`: launcher behavior and operational limitations.
- `assistant/MODELS.md`: 7B/8B/14B hardware tradeoffs and model acceptance order.
- `runner.py`, `cases.json`: model-driven OpenCode `probe` baseline and tool metrics.
- `deterministic_orchestration.mjs`: strongest working fixed serial MCP controller.
- `tests/deterministic_orchestration.test.mjs`: eight offline controller regression tests.
- `results/runs/`: published summaries; inspect the newest relevant report, not just its filename or process status.
- `local-results/`: local raw artifacts, never publish.
