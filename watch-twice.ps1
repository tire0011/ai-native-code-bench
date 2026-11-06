# Task Scheduler permits one-minute repetition; check twice per invocation.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'watch.ps1')
Start-Sleep -Seconds 30
& (Join-Path $PSScriptRoot 'watch.ps1')
