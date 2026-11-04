# Research foundation: AI-native program representations

## Research question

Can a language model solve programming tasks more reliably, quickly, or with less
compute when it writes a machine-oriented representation instead of traditional
source code? Can these benefits make small open-weight models more useful?

## Approaches worth comparing

1. **Conventional source code:** natural programming languages such as Python.
2. **Canonical/compact syntax:** [Tacit](https://github.com/weetster/tacit)
   treats an AST as authoritative and provides compact and inspection views.
3. **Structured code:** [Edict](https://github.com/Sowiedu/Edict) uses a JSON
   AST, typed compiler feedback, effect checking, contract verification and WASM.
4. **Latent program search:** neural models search learned representations of
   programs (e.g., [Latent Programmer](https://proceedings.mlr.press/v139/hong21a.html)
   and [Latent Program Networks](https://papers.nips.cc/paper_files/paper/2025/hash/95738b4062a7fed00bb9db468475ae53-Abstract-Conference.html)).

These are distinct techniques. Edict and Tacit are *not* vector-native latent
programming languages. LLVM SIMD vectorization, neural embeddings, and canonical
ASTs are also three different concepts.

## Working hypotheses (not established facts)

- H1: Structured compiler diagnostics reduce unsuccessful repair iterations.
- H2: Canonical representations can reduce end-to-end token usage.
- H3: Typed or constrained generation improves *functional* correctness, not
  merely syntactic validity.
- H4: Benefits may depend on model size, tokenizer, training data and context.
- H5: An independently verifiable intermediate representation could improve
  cross-model collaboration without needing shared proprietary weights.

## Key evidence and caveats

- [Type-Constrained Code Generation with Language Models (PLDI 2025)](https://doi.org/10.1145/3729274)
  found fewer compilation errors and better functional correctness on its tested tasks.
- [Grammar-Aligned Decoding (NeurIPS 2024)](https://papers.nips.cc/paper_files/paper/2024/hash/2bdc2267c3d7d01523e2e17ac0a754f3-Abstract-Conference.html)
  warns that naive grammar constraints can degrade output quality.
- [Unnatural Languages Are Not Bugs but Features for LLMs (ICML 2025)](https://proceedings.mlr.press/v267/duan25c.html)
  shows models can process semantically meaningful, human-unreadable strings;
  it does not prove those strings are superior programming languages.

## Open questions

- Is the benefit attributable to syntax, compiler feedback, tests, or training?
- Does token reduction survive counting schemas, examples, retries and tool calls?
- Can code be incrementally edited without regenerating entire modules?
- How do we inspect, audit, reproduce and safely execute agent-authored programs?
- Can a latent search process preserve exact semantics before verification?

The project begins with a deliberately limited plumbing smoke test. See
[methodology.md](methodology.md) before interpreting any results.
