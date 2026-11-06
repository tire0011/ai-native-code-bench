param([switch]$LiveOutput)
# One polling iteration; usable by foreground watcher or Task Scheduler.
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
    Log 'Checking GitHub for updates...'
    Invoke-GitChecked @('fetch', 'origin', 'main', '--quiet') | Out-Null
    $localHead = (Invoke-GitChecked @('rev-parse', 'HEAD') | Select-Object -First 1).Trim()
    $upstream = (Invoke-GitChecked @('rev-parse', 'origin/main') | Select-Object -First 1).Trim()
    if ($localHead -eq $upstream) { Log 'No changes'; return }
    $base = (Invoke-GitChecked @('merge-base', 'HEAD', 'origin/main') | Select-Object -First 1).Trim()
    $changes = @(Invoke-GitChecked @('diff', '--name-only', "$base..origin/main", '--', '.'))
    $rebased = $false
    if ($base -ne $localHead) {
        # Safe auto-rebase only when EVERY local-only commit changes benchmark result files.
        # User code commits and all uncommitted tracked files are never rebased.
        $localCommits = @(Invoke-GitChecked @('rev-list', 'origin/main..HEAD') | Where-Object { $_ })
        $safe = $localCommits.Count -gt 0
        foreach ($commit in $localCommits) {
            $paths = @(Invoke-GitChecked @('diff-tree', '--no-commit-id', '--name-only', '-r', $commit) | Where-Object { $_ })
            if ($paths.Count -eq 0 -or @($paths | Where-Object { $_ -notmatch '^results/(runs|logs)/' }).Count -gt 0) {
                $safe = $false
                break
            }
        }
        if (-not $safe) {
            Log 'Local-only commits include non-result files; refusing automatic rebase.'
            return
        }
        Log "Rebasing $($localCommits.Count) local result-only commit(s) onto origin/main..."
        $rebaseOutput = & git.exe rebase origin/main 2>&1
        if ($LASTEXITCODE -ne 0) {
            Log 'Rebase conflicted; aborting to preserve original local commits.'
            & git.exe rebase --abort 2>&1 | Out-Null
            return
        }
        $localHead = (Invoke-GitChecked @('rev-parse', 'HEAD') | Select-Object -First 1).Trim()
        Log 'Result-only commits safely rebased.'
        $rebased = $true
    }
    $needRun = @($changes | Where-Object { $_ -and $_ -notmatch '^results/(runs|logs)/' }).Count -gt 0
    Log "Remote update found ($($changes.Count) changed paths); benchmark rerun: $needRun"
    if ($rebased) {
        # Rebase may leave our result commits ahead of origin/main; publish them
        # before running tests so the next polling iteration does not repeat the rebase.
        Invoke-GitChecked @('push', 'origin', 'main') | Out-Null
        Log 'Rebased result commits uploaded.'
    }
    else {
        Invoke-GitChecked @('pull', '--ff-only', 'origin', 'main') | Out-Null
    }
    if (-not $needRun) {
        Log 'Only benchmark results/logs changed; synchronized without running.'
        return
    }
    Log 'Starting local Qwen benchmark.'
    $runLog = Join-Path $logDir ("watch-run-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    if ($LiveOutput) {
        & (Join-Path $PSScriptRoot 'run.ps1') -NoWatch *>&1 | Tee-Object -FilePath $runLog
    }
    else {
        & (Join-Path $PSScriptRoot 'run.ps1') -NoWatch *> $runLog
    }
    $runExit = $LASTEXITCODE
    Log "Benchmark finished with exit code $runExit; log: $runLog"
}
catch { Log "Watcher error: $($_.Exception.Message)" }
finally {
    if ($acquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
