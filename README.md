# AI-Native Code Bench

[![Tests](https://github.com/tire0011/ai-native-code-bench/actions/workflows/tests.yml/badge.svg)](https://github.com/tire0011/ai-native-code-bench/actions/workflows/tests.yml)

Open, reproducible experiments on whether machine-oriented programming
representations help small language models generate **correct programs with
less total compute**.

This is an independent community research project, not affiliated with Tacit,
Edict, OpenEuroLLM, or any model provider. Contributions and negative results
are welcome.

## Why?

Traditional languages prioritize human authorship. [Tacit](https://github.com/weetster/tacit)
explores canonical compact program representations, while
[Edict](https://github.com/Sowiedu/Edict) provides a JSON AST with typed compiler
feedback, contracts, and WASM compilation. We want to measure what helps actual
code-generation success: syntax, structured feedback, constrained generation,
model training, or some combination.

Longer-term questions include latent/vector-based program search and
interoperability across independent open-weight models. Neither Tacit nor Edict
is currently a neural latent-vector programming language.

Read the [research foundation](docs/research.md) and
[evaluation methodology](docs/methodology.md).

## Status

**Milestone 0: smoke-test harness.** The first three tasks verify that the
Ollama/Python and Ollama/Edict paths can generate, compile, execute and produce
machine-readable results. They are intentionally trivial and **must not be
used for performance claims**. A controlled, held-out benchmark follows.

## Quick start (PowerShell, Windows)

Prerequisites: Python 3.11+, Node.js/npm, Ollama, Docker Desktop (running).

```powershell
git clone https://github.com/tire0011/ai-native-code-bench.git
Set-Location ai-native-code-bench
ollama pull qwen2.5-coder:7b
npm install
docker pull python:3.12-alpine
python -m unittest discover -s tests -v
python -m bench --model qwen2.5-coder:7b --mode both
```

The runner uses Ollama at `http://127.0.0.1:11434`. Change the endpoint with
`--endpoint` if necessary. JSONL results go to `results/smoke.jsonl` and include
all generated artifacts and failures. The directory is gitignored by default.
Edict defaults to two additional compiler-feedback repair attempts if the
initial AST is invalid. Every generation (including failures) contributes to
the reported tokens and duration. For a first-attempt-only run, use:

```powershell
python -m bench --mode edict --max-edict-repairs 0
```

### Compare Edict prompting approaches

Run all three variants using the same Ollama model, tasks and decoding settings:

```powershell
python -m bench --mode edict --edict-prompt all --output results/edict-prompts.jsonl
```

| Profile | Context given to the model |
| --- | --- |
| `baseline` | Original short instructions and two small AST examples (unchanged) |
| `official` | `edict_schema` and `edict_examples` fetched from the installed Edict MCP server, with a deterministic 8,000-character excerpt budget |
| `compact` | Short Edict authoring guide covering JSON node shapes, `toString`, bindings and common false assumptions |

Use `--edict-prompt official` or `--edict-prompt compact` for individual runs.
`--edict-doc-chars 12000` changes the total excerpt budget, but can exceed
the effective context budget of smaller Ollama models. The JSONL output records
the profile, all model tokens including retries, model time, wall-clock time,
and a SHA-256 of the full installed documentation sources for the `official`
profile. The schema/examples are excerpted: this is *documentation-assisted
prompting*, not a claim that the complete schema fits in the context window.

These three tasks remain **integration smoke tests**, not reliable accuracy
statistics. Compare both success and total token cost, not only pass rates.

Repeated Edict AST node IDs are deterministically renamed before compilation;
the original model output and each normalization are preserved in the JSONL
record. This is a *tooling intervention*, not evidence that the model generated
valid Edict unaided. WASM instantiation errors are reported separately rather
than passed back to the model as if they were AST errors.

For an initial generation-only test without executing any generated program:

```powershell
python -m bench --mode both --no-execute
```

To test only one arm:

```powershell
python -m bench --mode edict
python -m bench --mode python
```

Edict version `1.23.2` is pinned in `package.json`. Its MCP server is spawned
locally via `npx --no-install edict-lang` and queried for tool input schemas.
An initial Windows/Ollama run confirmed `factorial-6` produces `720` after
compiler-guided repair. Other smoke tasks still expose generation errors and
an invalid WASM binary, so **Edict execution is not yet fully validated**.

### Diagnose an Edict WASM failure

The repository includes a sanitized, real model-generated AST that passed
Edict 1.23.2 compilation but failed WASM validation (`i32.store` stack
underflow). To replay it **without Ollama or another model call**:

```powershell
python -m bench.repro
```

Or replay the most recent compiled AST for a task in your own result file:

```powershell
python -m bench.repro --input results/smoke.jsonl --task even-sum-20
```

The diagnostic runs four independent cases: original AST, original without
the string expression, without the block, and without either. It reports
compiler errors separately from WASM execution errors, to help isolate an
Edict code-generation problem. The modified variants **do not preserve program
semantics** and their outputs must not be scored as task successes. The original
AST itself contains an erroneous assumption that a `block` repeats like a loop;
even valid WASM would not establish that the model solved the task.

## Safety

**Never execute untrusted generated code directly on your host.** The Python
runner requires Docker and uses a read-only container with no network access,
dropped Linux capabilities and time/resource limits. Docker is not a perfect
sandbox; for untrusted models or adversarial code, use a disposable VM.
Edict WASM host capabilities must be independently reviewed before extending
the runner to filesystem/network access.

Do not run private corporate code or publish credentials in benchmark results.

## Roadmap

- [x] Independent, open research framing and initial local harness
- [x] Ollama model driver with token/time accounting
- [x] Python container runner and Edict MCP client
- [ ] Verify both execution paths with live Qwen2.5-Coder-7B on Windows
- [ ] Held-out input/output oracles and equivalent language coverage
- [ ] Replicated runs, reporting with uncertainty, additional open-weight models
- [ ] Tacit compact-view baseline and structured Python-edit control
- [ ] Latent program search feasibility study

MIT-licensed. See [LICENSE](LICENSE).
