# One-shot entrypoint for the extracted git-repo-poller.
# Reuses the benchmark's EXISTING run.ps1 and result publishing. Never starts
# the benchmark's legacy foreground watcher, which remains paused.
[CmdletBinding()]
param([switch]$NoPush)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'run.ps1') -NoWatch -NoPush:$NoPush
exit $LASTEXITCODE
