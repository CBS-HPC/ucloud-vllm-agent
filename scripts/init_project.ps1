param(
    [string]$VenvRoot = (Join-Path $env:LOCALAPPDATA 'ucloud-vllm-agent\venv'),
    [switch]$Dev
)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $VenvRoot 'Scripts\python.exe'))) {
    python -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}
$AgentPython = Join-Path $VenvRoot 'Scripts\python.exe'
$InstallTarget = if ($Dev) { "$RepoRoot[dev]" } else { $RepoRoot }
& $AgentPython -m pip install -e $InstallTarget
if ($LASTEXITCODE -ne 0) { throw 'Could not install the agent.' }
Write-Host "Environment ready: $VenvRoot"
