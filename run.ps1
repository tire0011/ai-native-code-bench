param(
    [string]$Model = 'ollama/qwen2.5-coder:7b',
    [string]$Cases = '',
    [int]$TimeoutSeconds = 360,
    [switch]$NoPush,
    [switch]$NoWatch
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host "[$(Get-Date -Format HH:mm:ss)] Benchmark model: $Model"
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Runner unit tests failed' }

python -u runner.py --model $Model --cases $Cases --timeout $TimeoutSeconds
$runExit = $LASTEXITCODE
# Install/cache Aider and SCIP locally and publish lightweight success metrics.
# Failures are recorded by context_probe.py without interrupting the existing benchmark.
python -u context_probe.py
if ($LASTEXITCODE -ne 0) { Write-Warning 'Context probe could not complete; existing benchmark results are retained.' }
if ($NoPush) {
    Write-Host 'Upload skipped (-NoPush)'
}
else {
    # Reconcile concurrent GitHub writes without rebasing code commits.
    & (Join-Path $PSScriptRoot 'sync-results.ps1') -CommitPending
    if (-not $?) { throw 'Result synchronization failed; local results retained' }
}
if ($runExit -ne 0) { Write-Warning "Benchmark failed with exit code $runExit" }
if (-not $NoWatch) {
    Write-Host 'Starting foreground GitHub watcher (Ctrl+C to stop)...'
    & (Join-Path $PSScriptRoot 'watch-loop.ps1')
}
exit $runExit
