param(
    [Parameter(Mandatory=$true)][string]$Model,
    [string]$Cases = '',
    [int]$TimeoutSeconds = 360
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python runner.py --model $Model --cases $Cases --timeout $TimeoutSeconds
exit $LASTEXITCODE
