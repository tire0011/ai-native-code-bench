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
The first live Edict integration run still needs to be verified on a machine
with the package installed; please open an issue with sanitized logs if you
encounter a schema mismatch.

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
