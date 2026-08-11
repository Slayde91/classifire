param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRoot,

    [string]$WorkspaceRoot = "C:\CLASSIFIRE-OpenClaw"
)

$ErrorActionPreference = "Stop"

$manifestPath = Join-Path $SourceRoot "FLEET_MANIFEST.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Fleet manifest not found: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

foreach ($spec in $manifest.agents) {
    $source = Join-Path (Join-Path $SourceRoot "agents") $spec.id
    $target = Join-Path $WorkspaceRoot $spec.id
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Agent source folder missing: $source"
    }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Get-ChildItem -LiteralPath $source -Filter "*.md" -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $target $_.Name) -Force
    }
    Write-Host "Installed markdown definitions for $($spec.id)" -ForegroundColor Green
}

Write-Host ""
Write-Host "All CLASSIFIRE agent markdown definitions installed." -ForegroundColor Green
