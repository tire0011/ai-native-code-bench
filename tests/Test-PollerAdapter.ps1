# Offline adapter test: never invokes the real benchmark, model or network.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('bench-poller-adapter-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $root | Out-Null
try {
    Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'poller-run.ps1') -Destination (Join-Path $root 'poller-run.ps1')
    @'
param([switch]$NoWatch, [switch]$NoPush)
if (-not $NoWatch) { exit 21 }
if ([bool]$NoPush -ne ($env:BENCH_STUB_EXPECT_NOPUSH -eq '1')) { exit 22 }
Set-Content -LiteralPath $env:BENCH_STUB_MARKER -Value 'ran exactly once'
exit 0
'@ | Set-Content -LiteralPath (Join-Path $root 'run.ps1') -Encoding utf8
    $env:BENCH_STUB_MARKER = Join-Path $root 'marker.txt'
    $env:BENCH_STUB_EXPECT_NOPUSH = '0'
    & pwsh -NoProfile -NonInteractive -File (Join-Path $root 'poller-run.ps1')
    if ($LASTEXITCODE -ne 0) { throw "Default adapter failed: exit $LASTEXITCODE" }
    if ((Get-Content -LiteralPath $env:BENCH_STUB_MARKER) -ne 'ran exactly once') { throw 'Missing run marker' }
    Remove-Item -LiteralPath $env:BENCH_STUB_MARKER
    $env:BENCH_STUB_EXPECT_NOPUSH = '1'
    & pwsh -NoProfile -NonInteractive -File (Join-Path $root 'poller-run.ps1') -NoPush
    if ($LASTEXITCODE -ne 0) { throw "NoPush adapter failed: exit $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $env:BENCH_STUB_MARKER)) { throw 'NoPush run missing' }
    Write-Output 'PASS: adapter invokes the existing run.ps1 once, always -NoWatch, preserves optional -NoPush.'
} finally {
    Remove-Item Env:BENCH_STUB_MARKER -ErrorAction SilentlyContinue
    Remove-Item Env:BENCH_STUB_EXPECT_NOPUSH -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
