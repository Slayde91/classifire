param(
    [string]$RunId = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [int]$TimeoutSeconds = 300,
    [string]$BaseUrl = "http://127.0.0.1:8787"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = Join-Path $repoRoot "scripts\classifire_uat_launcher.py"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "CLASSIFIRE managed UAT launcher is missing: $launcher"
}

& $python.Source $launcher `
    --run-id $RunId `
    --timeout-seconds $TimeoutSeconds `
    --base-url $BaseUrl

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "CLASSIFIRE managed UAT launcher failed with exit code $exitCode."
}
