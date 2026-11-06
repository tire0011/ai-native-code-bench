param(
    [string]$Model = 'ollama/qwen2.5-coder:7b',
    [string]$Cases = '',
    [int]$TimeoutSeconds = 360,
    [switch]$NoPush
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
    exit $runExit
}

# Only auto-push public benchmark results/logs on our own main branch.
$branch = (git branch --show-current).Trim()
$remote = (git remote get-url origin).Trim()
if ($branch -ne 'main' -or $remote -notmatch '^(https://github\.com/|git@github\.com:|ssh://git@github\.com/)tire0011/ai-native-code-bench(\.git)?$') {
    Write-Warning "No auto-push: branch=$branch, origin=$remote"
    exit $runExit
}
$changed = @(git status --porcelain -- results/runs results/logs)
if ($changed.Count -gt 0) {
    Write-Host "[$(Get-Date -Format HH:mm:ss)] Commit results..."
    git add -- results/runs results/logs
    if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
    git commit -m "Benchmark run $Model $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
    Write-Host "[$(Get-Date -Format HH:mm:ss)] Push results..."
    git push origin main
    if ($LASTEXITCODE -ne 0) { throw 'git push failed; local commit retained' }
    Write-Host "[$(Get-Date -Format HH:mm:ss)] Results uploaded to GitHub"
}
if ($runExit -ne 0) { Write-Warning 'Benchmark failed; diagnostic summary uploaded' }
exit $runExit
