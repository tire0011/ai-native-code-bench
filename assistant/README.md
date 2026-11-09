# Local C# assistant profile

`local.ps1` prepares and launches an entirely local OpenCode session for a C# solution.

From the repository root:

```powershell
# Validate/setup without opening the interactive UI.
.\local.ps1 -SetupOnly -SmokeTest

# Start OpenCode on the public CleanArchitecture fixture.
.\local.ps1

# Use another already-installed base model or ignored workspace checkout.
.\local.ps1 -BaseModel qwen2.5-coder:7b
.\local.ps1 -ProjectPath workspaces/AnotherPublicRepo
```

If the base model is missing, the script deliberately does not download it without an explicit decision:

```powershell
ollama pull qwen3:8b
```

## What it configures

- A `csharp-local` Ollama alias sharing blobs with its base model; weights are not duplicated.
- 8,192 context tokens, temperature 0.1, and a 4,096-token generation ceiling by default. Override the first two model choices with `-BaseModel` and context with `-ContextTokens`.
- Ollama bound to loopback, cloud disabled, one loaded model, one request at a time, flash attention, q8_0 KV cache, and a 30-minute keep-alive for servers started by the script.
- An OpenCode profile that permits only the Ollama provider, denies web tools, limits retained tool output, exposes 15 core Roslyn MCP tools directly (`codemode: false`) instead of burying them in the full 67-tool catalog, disables the unrelated Azure server, denies small-model subagent delegation, and gives all helper agents the same local model.
- A generated `.opencode/opencode.jsonc` in the target project. Existing non-generated config is never overwritten.

An already-running Ollama server retains its old startup environment. The script warns about this. To apply every performance setting, quit/stop that server before launching the script; do not terminate a server with active work just to change settings.

After the model is preloaded, `ollama ps` shows the actual processor split and allocated context. `100% GPU` is preferred. Partial CPU offload can be useful for larger models but is slower and is not the default target for this 8 GiB GPU.

**Verified on this machine (2026-11-09):** the default Qwen3 alias preloaded with **8,192 context tokens**, **6.2 GB** reported model allocation, and **100% GPU**. The OpenCode smoke run returned exactly `LOCAL_OK`. The same server's pre-existing startup environment was retained during this check; a fresh launcher-started server additionally applies the q8_0 KV-cache setting. These are infrastructure checks, not proof of autonomous C# task quality; keep using `runner.py` and real builds/tests for that.

OpenCode configuration discovery can include user-level plugins and MCP servers. Provider policies block non-Ollama inference and the generated permissions deny web tools, but review unrelated machine-global plugins before using this profile with sensitive code. This repository's results watcher is separate and is not started by `local.ps1`.

The local model is an assistant, not an authority. Require a final diff plus real `dotnet build`/`dotnet test` evidence before accepting changes.

See [MODELS.md](MODELS.md) for measured 7B/8B choices, optional 14B experiments, and why semantic retrieval matters more than a large advertised context window.

To test deterministic Roslyn navigation without an LLM or OpenCode agent loop, run `node deterministic_orchestration.mjs` from the repository root. The controller uses the official MCP SDK directly, calls a fixed serial plan, and writes compact metrics to `results/runs/` plus raw MCP responses only to ignored `local-results/`.
