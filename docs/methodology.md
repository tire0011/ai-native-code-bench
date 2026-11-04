# Evaluation protocol and limitations

## Milestone 0: integration smoke test (current)

- One fixed Ollama model, deterministic decoding settings (`temperature=0`, `seed=42`).
- Three elementary output-only tasks in `tasks/smoke.json`.
- Python produces source code, then runs inside an isolated Docker container.
- Edict produces a JSON AST, then the installed MCP compiler and WASM runtime
  are invoked. Incompatible tool schemas/results fail explicitly rather than
  silently counting a compile as a functional success.
- Each response records model tokens, time, raw artifact, diagnostics and errors.
- Both modes are scored on the same expected output when integration succeeds.
  This is still only a smoke test: do not publish an accuracy comparison from
  these tasks. Its goal is to expose integration problems.

These tasks can be solved by printing constants: they are *not* a trustworthy
measure of programming ability. Even identical fixed tasks are insufficient to
claim generalization. We intentionally keep the initial smoke test small.

## Milestone 1: comparative benchmark (planned)

1. Test both languages against equivalent independent input/output oracles.
2. Use held-out functional inputs, property-based tests and negative examples.
3. Balance task coverage with each language's actually implemented features.
4. Use 20–50 tasks, at least 3 runs per task/arm, paired by model and seed.
5. Keep model, quantization, sampling, context and budgets fixed; log exact versions.
6. Count **all** prompt, completion, schema, compiler-feedback and retry tokens.
7. Report pass@1, success at fixed budget, time, tokens per successful task,
   failures by stage, and uncertainty intervals; retain all failed trials.
8. Add a Python structured-edit baseline to separate *tooling effects* from
   *language effects*.

## Milestone 2: model and representation research (planned)

- Test distinct small and medium open-weight models with identical harnesses.
- Compare Tacit's compact view and Edict's AST patch protocol.
- Consider fine-tuning on *train-only* examples, with sealed evaluation tasks.
- Investigate latent/vector program search only after symbolic baselines exist.

## Security and reproducibility

Generated code is untrusted. Never execute it directly on your workstation.
The Python runner **requires Docker**, disables networking, drops privileges,
uses read-only mounts and applies time/resource limits. Docker is defense in
depth, not a complete security boundary; prefer a disposable VM for hostile
models or unfamiliar programs. The Edict WASM runtime must be separately
reviewed before granting filesystem, HTTP or other host capabilities.

Pin Edict to a version; pin Docker images by digest for the research-grade
benchmark. Publish all task fixtures, scripts, evaluation protocol, raw records,
model/version identifiers and relevant hardware configuration. Never commit
private source code or credentials.
