param([switch]$CommitPending)
# Safe synchronization of benchmark metrics; never force push or rebase user code.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Git([string[]]$Arguments) {
    $output = @(& git.exe @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed: $($output -join ' ')" }
    return $output
}
$remote = (Git @('remote', 'get-url', 'origin') | Select-Object -First 1).Trim()
$branch = (Git @('branch', '--show-current') | Select-Object -First 1).Trim()
if ($branch -ne 'main' -or $remote -notmatch '^(https://github\.com/|git@github\.com:|ssh://git@github\.com/)tire0011/ai-native-code-bench(\.git)?$') {
    throw 'Automatic benchmark push requires the expected origin and main branch.'
}
$tracked = @(Git @('diff', '--name-only', 'HEAD') | Where-Object { $_ })
$outside = @($tracked | Where-Object { $_ -notmatch '^results/(runs|logs)/' })
if ($outside.Count -gt 0) {
    throw "Non-result tracked changes detected: $($outside -join ', '). Leaving local work untouched."
}
$staged = @(Git @('diff', '--cached', '--name-only') | Where-Object { $_ })
if (@($staged | Where-Object { $_ -notmatch '^results/(runs|logs)/' }).Count -gt 0) {
    throw 'Non-result files are staged. Refusing automatic commit/rebase.'
}
if ($CommitPending) {
    $pending = @(Git @('status', '--porcelain', '--', 'results/runs', 'results/logs') | Where-Object { $_ })
    if ($pending.Count -gt 0) {
        Git @('add', '--', 'results/runs', 'results/logs') | Out-Null
        Git @('commit', '-m', ('Benchmark results ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))) | Out-Null
        Write-Host 'Committed local benchmark results.'
    }
}
if (@(Git @('status', '--porcelain', '--untracked-files=no') | Where-Object { $_ }).Count -gt 0) {
    throw 'Tracked working-tree changes remain. Refusing rebase.'
}

for ($attempt = 1; $attempt -le 4; $attempt++) {
    Git @('fetch', 'origin', 'main', '--quiet') | Out-Null
    $local = (Git @('rev-parse', 'HEAD') | Select-Object -First 1).Trim()
    $upstream = (Git @('rev-parse', 'origin/main') | Select-Object -First 1).Trim()
    if ($local -ne $upstream) {
        $commits = @(Git @('rev-list', '--reverse', 'origin/main..HEAD') | Where-Object { $_ })
        foreach ($sha in $commits) {
            $parents = ((Git @('rev-list', '--parents', '-n', '1', $sha) | Select-Object -First 1) -split '\s+')
            if ($parents.Count -ne 2) { throw "Local merge/root commit $sha requires manual review." }
            $paths = @(Git @('diff-tree', '--no-commit-id', '--name-only', '-r', $sha) | Where-Object { $_ })
            if ($paths.Count -eq 0 -or @($paths | Where-Object { $_ -notmatch '^results/(runs|logs)/' }).Count -gt 0) {
                throw "Local commit $sha contains non-result files. No automatic rebase."
            }
        }
        if ($commits.Count -gt 0) {
            Write-Host "Rebasing $($commits.Count) result-only commit(s) on origin/main..."
            & git.exe rebase origin/main
            if ($LASTEXITCODE -ne 0) {
                & git.exe rebase --abort 2>&1 | Out-Null
                throw 'Rebase conflicted; aborted without discarding local commits.'
            }
        }
        else {
            Git @('merge', '--ff-only', 'origin/main') | Out-Null
        }
    }
    $ahead = @(Git @('rev-list', 'origin/main..HEAD') | Where-Object { $_ })
    if ($ahead.Count -eq 0) { return }
    Write-Host "Publishing result-only commits (attempt $attempt/4)..."
    & git.exe push origin main
    if ($LASTEXITCODE -eq 0) { Write-Host 'Results uploaded to GitHub'; return }
    Start-Sleep -Seconds 2
}
throw 'Upload did not succeed after four attempts; local commits preserved.'
