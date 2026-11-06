# Foreground watcher: stays in this PowerShell window until Ctrl+C.
param([int]$IntervalSeconds = 30)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($IntervalSeconds -lt 5) { throw 'Interval must be >= 5 seconds' }
Write-Host "Watching GitHub from $PSScriptRoot every $IntervalSeconds seconds. Ctrl+C to stop."
Write-Host 'Note: disable the old scheduled task to avoid duplicate checks.'
$pauseFile = Join-Path $PSScriptRoot 'local-results/watcher.paused'
if (Test-Path -LiteralPath $pauseFile) {
    Remove-Item -LiteralPath $pauseFile -Force
    Write-Host 'Removed stale pause marker: foreground watcher explicitly restarted.'
}
while ($true) {
    try {
        & (Join-Path $PSScriptRoot 'watch.ps1') -LiveOutput
    }
    catch {
        Write-Warning "Watcher iteration failed: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $IntervalSeconds
}
