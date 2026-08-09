param(
    [string]$RunId = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [int]$TimeoutSeconds = 300,
    [string]$BaseUrl = "http://127.0.0.1:8787"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runner = Join-Path $repoRoot "scripts\run_classifire_openclaw_reference_uat.py"

if (-not (Test-Path -LiteralPath $runner)) {
    throw "CLASSIFIRE Python UAT controller is missing: $runner"
}

& $python.Source $runner `
    --run-id $RunId `
    --timeout-seconds $TimeoutSeconds `
    --base-url $BaseUrl

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "CLASSIFIRE Python UAT controller failed with exit code $exitCode."
}
