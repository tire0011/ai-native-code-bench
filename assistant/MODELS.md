# Local model choices for this machine

The goal is the best verified C# change per working session, not the largest parameter count that technically starts. This machine has an NVIDIA RTX 2000 Ada Laptop GPU with 8 GiB VRAM and 32 GiB RAM.

| Candidate | Approx. local download | Role on this machine | Evidence/limitation |
| --- | ---: | --- | --- |
| `qwen3:8b` Q4_K_M | 5.2 GB | Default OpenCode agent candidate | Official Ollama metadata advertises tools and reasoning. In the first public fixture run it made a real built-in file read; Roslyn behavior depends on the MCP/profile configuration and is evaluated with `runner.py`. |
| `qwen2.5-coder:7b` Q4_K_M | 4.7 GB | Lightweight code-edit/context alternative | A prior focused repair with precise API context and compiler feedback passed 21/21 tests. Earlier OpenCode runs produced no genuine built-in or Roslyn tool calls, so do not assume it is an autonomous agent. |
| `qwen3:14b` | about 9 GB | Optional quality experiment | Not installed or measured here. Expect partial CPU offload on 8 GiB VRAM. Compare correctness and speed only after the 8B profile passes its tool checks. |
| `qwen2.5-coder:14b` Q4_K_M | 9.0 GB | Optional code-quality experiment | Not installed or measured here. Also exceeds VRAM before context/cache overhead. Being code-specialized does not fix tool-routing problems by itself. |
| 30B+ dense/MoE models | roughly 18+ GB | Not the daily target | Can be made to run with RAM/CPU offload in some configurations, but leaves little headroom on a 32 GiB workstation and risks slow tool loops. No such model is required by this repository. |

## Switch an already-installed model

```powershell
.\local.ps1 -BaseModel qwen2.5-coder:7b
```

For an optional 14B experiment, make the download an explicit decision:

```powershell
ollama pull qwen3:14b
.\local.ps1 -BaseModel qwen3:14b -ContextTokens 8192
```

The `csharp-local` alias is recreated with that base. Check actual memory placement:

```powershell
ollama ps
```

- Prefer `100% GPU` for interactive work.
- A CPU/GPU split is an explicit speed/quality tradeoff, not a failure and not something to hide.
- If another application claims VRAM, the same model can offload differently. Measure under representative workload.
- Do not load multiple large models concurrently. The launcher requests one model and one inference stream for servers it starts.

## Context strategy

Ollama currently defaults to 4K context below 24 GiB VRAM. The local profile deliberately creates an 8K alias and verifies that allocation with `ollama ps`; configured context and actual allocated context are different things.

Eight thousand tokens is not enough to “ingest” a large C# solution. Scaling instead comes from:

1. Roslyn load/symbol/navigation tools on actual solution structure.
2. Narrow reads for implicated files and dependency API documentation.
3. Small coherent edits rather than whole-repository rewrites.
4. Focused compiler/test diagnostics and bounded tool output.
5. New sessions for unrelated tasks instead of an ever-growing conversation.

Flash attention and q8_0 KV cache reduce pressure for servers started by `local.ps1`. A pre-existing server keeps its old environment, which the launcher reports. Do not raise `-ContextTokens` merely because the model card advertises 32K/128K/256K: verify quality, latency, and the `ollama ps` processor split on this GPU.

## Acceptance order

Choose the default in this order:

1. Correct C# changes with passing real tests and preserved compatibility.
2. Genuine direct tool events and correct symbol/file results (not printed pseudo-tool calls).
3. Stable single-model local operation without silent cloud fallback.
4. GPU placement, latency, token use, and download/memory cost.

A larger model earns a place only if it improves the earlier criteria enough to justify its offload and runtime cost.
