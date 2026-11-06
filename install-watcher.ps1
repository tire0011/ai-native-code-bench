# Install user-level Windows scheduled task; runs while signed in.
$ErrorActionPreference = 'Stop'
$taskName = 'AI Native Code Bench Watcher'
$script = Join-Path $PSScriptRoot 'watch-twice.ps1'
$ps = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $ps) { $ps = (Get-Command powershell.exe -ErrorAction Stop).Source }
$arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $script
$action = New-ScheduledTaskAction -Execute $ps -Argument $arguments -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Installed task: $taskName (about every 30 seconds, when signed in)."
Write-Host "Local log: $PSScriptRoot\local-results\watch.log"
Write-Host "Test now: .\watch.ps1"
