param([switch]$LiveOutput)
# Called once by Windows Task Scheduler every 5 minutes.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$logDir = Join-Path $PSScriptRoot 'local-results'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logPath = Join-Path $logDir 'watch.log'
function Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Write-Host $line
    Add-Content -LiteralPath $logPath -Value $line
}
function Invoke-GitChecked([string[]]$Arguments) {
    $output = & git.exe @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Git command failed: $($output -join ' ')" }
    return @($output)
}
$mutex = [System.Threading.Mutex]::new($false, 'Local\ai-native-code-bench-watcher')
$acquired = $false
try {
    $acquired = $mutex.WaitOne(0)
    if (-not $acquired) { Log 'Previous watch/test is still running; skipping.'; return }
    $remote = (Invoke-GitChecked @('remote', 'get-url', 'origin') | Select-Object -First 1).Trim()
    $branch = (Invoke-GitChecked @('branch', '--show-current') | Select-Object -First 1).Trim()
    if ($branch -ne 'main' -or $remote -notmatch '^(https://github\.com/|git@github\.com:|ssh://git@github\.com/)tire0011/ai-native-code-bench(\.git)?$') {
        Log "Skipping: unexpected branch or remote: $branch $remote"
        return
    }
    if (@(Invoke-GitChecked @('status', '--porcelain', '--untracked-files=no')).Count -gt 0) {
        Log 'Tracked local changes detected; skipping pull to protect work.'
        return
    }
    Invoke-GitChecked @('fetch', 'origin', 'main', '--quiet') | Out-Null
    $localHead = (Invoke-GitChecked @('rev-parse', 'HEAD') | Select-Object -First 1).Trim()
    $upstream = (Invoke-GitChecked @('rev-parse', 'origin/main') | Select-Object -First 1).Trim()
    if ($localHead -eq $upstream) { return }
    $base = (Invoke-GitChecked @('merge-base', 'HEAD', 'origin/main') | Select-Object -First 1).Trim()
    if ($base -ne $localHead) {
        Log 'Local main has diverged/ahead commits; refusing automatic pull.'
        return
    }
    $changes = @(Invoke-GitChecked @('diff', '--name-only', 'HEAD..origin/main', '--', '.'))
    $needRun = @($changes | Where-Object { $_ -and $_ -notmatch '^results/runs/' }).Count -gt 0
    Log "Remote update found ($($changes.Count) changed paths); benchmark rerun: $needRun"
    Invoke-GitChecked @('pull', '--ff-only', 'origin', 'main') | Out-Null
    if (-not $needRun) {
        Log 'Only benchmark results changed; synchronized without running.'
        return
    }
    Log 'Starting local Qwen benchmark.'
    $runLog = Join-Path $logDir ("watch-run-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    if ($LiveOutput) {
        & (Join-Path $PSScriptRoot 'run.ps1') *>&1 | Tee-Object -FilePath $runLog
    }
    else {
        & (Join-Path $PSScriptRoot 'run.ps1') *> $runLog
    }
    $runExit = $LASTEXITCODE
    Log "Benchmark finished with exit code $runExit; log: $runLog"
}
catch { Log "Watcher error: $($_.Exception.Message)" }
finally {
    if ($acquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
