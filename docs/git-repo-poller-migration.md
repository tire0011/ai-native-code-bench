# Extracting the benchmark watcher into git-repo-poller

This is the **compatibility/migration half** of [ai-native-code-bench#3](https://github.com/tire0011/ai-native-code-bench/issues/3), paired with the standalone [git-repo-poller PR #2](https://github.com/tire0011/git-repo-poller/pull/2).

The generic poller is not another benchmark engine. It replaces only the **polling/launch orchestration** in `watch.ps1` / `watch-loop.ps1`. The benchmark continues to own `run.ps1` and `sync-results.ps1`.

## Behavior mapping

| Existing benchmark behavior | Reusable poller / adapter |
| --- | --- |
| `watch-loop.ps1` periodic check and mutex | Installed launcher + Windows Task Scheduler and mutex |
| `watch.ps1` checks fixed repo/branch and refuses unsafe code changes | Per-experiment configured remote/branch, clean tree, fast-forward only |
| Relevant code changes trigger tests, `results/runs/` and `results/logs/` do not | `runOnChange: true` plus `ignorePaths` prefixes |
| `watch.ps1` invokes `run.ps1 -NoWatch` | New `poller-run.ps1` invokes the **existing** `run.ps1 -NoWatch` |
| `run.ps1` publishes benchmark results via `sync-results.ps1` | Unchanged during the run; the poller can also reconcile pending result-only changes before the next poll via an adapted reusable sync helper |
| `local-results/watcher.paused` prevents old watcher | Remains in effect for legacy watcher; new launcher uses its own `paused.flag` |
| Results-only local commit rebase / dirty-result recovery | Extracted into the generic poller's optional `sync-results.ps1` (parameterized repo, branch, `resultPaths`) with original commit/rebase/push guards; disabled for experiments with no `resultPaths` |

**Important:** The prior results-only recovery gap is now implemented in the standalone poller. Its **offline integration test** covers result commit/push, result-only no-rerun, local result rebase after new remote code, and refusal to rebase local code commits. This does not yet prove live Windows benchmark behavior; keep the original watcher paused until the actual host test passes.

## Example profile

In the **poller's local config**, select:

```json
{
  "id": "local-benchmark",
  "repo": "https://github.com/tire0011/ai-native-code-bench.git",
  "branch": "main",
  "entrypoint": "poller-run.ps1",
  "timeoutSeconds": 3600,
  "runOnChange": true,
  "ignorePaths": ["results/runs/", "results/logs/"],
  "resultPaths": ["results/runs/", "results/logs/"]
}
```

The adapter defaults to the benchmark's existing result publisher; for a local manual one-shot verification you can pass `-NoPush` to the adapter itself. Do **not** configure the poller to invoke `run.ps1` directly: that script starts `watch-loop.ps1` unless `-NoWatch` is supplied.

## Non-invasive validation

1. Offline: `pwsh -NoProfile -File .\tests\Test-PollerAdapter.ps1` uses a **fake** `run.ps1`; no GPU, Ollama or results publishing.
2. Standalone: run `git-repo-poller` `tests/Smoke.Tests.ps1` and `tests/ResultSync.Tests.ps1` on local bare Git remotes; confirm update routing, results-only commit/push/rebase, no false reruns, and preservation of local code commits.
3. Inspect current local benchmark results before enabling anything. Keep the original benchmark watcher **paused**; disable any old Task Scheduler job, but do not delete its scripts or pause marker.
4. On a trusted Windows host only after review, configure the new poller, initially **without Task Scheduler**. Read-only configuration check first; then authorize a one-shot benchmark run and verify local result publishing.
5. Test a results-only remote commit, a failed result upload, an offline fetch and a new code commit. Check that exactly one run occurs and that output stays out of public Git except the explicitly intended benchmark metrics.
6. After this regression passes, choose the new poller as the single scheduler. Do not run old and new watchers at once.

## Independent poller update

The stable launcher and local config are installed outside experiment worktrees; it may update the generic poller between ticks. That update cannot change a running experiment process. If a new poller version fails, switch to the last good snapshot. Experiment repositories update separately.

The goal is **one generic poller** used for the benchmark and any other authorized experiment, not a second watcher implementation living alongside the benchmark forever.
