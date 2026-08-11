param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRoot,

    [string]$MissionControlUrl = "http://127.0.0.1:3000",

    [string]$RepoEnvFile = "C:\CLASSIFIRE\.env"
)

$ErrorActionPreference = "Stop"

function Get-DotEnvValue {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Environment file not found: $Path"
    }
    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -like "$Name=*" } |
        Select-Object -First 1
    if (-not $line) {
        throw "$Name was not found in $Path"
    }
    return $line.Substring($line.IndexOf("=") + 1)
}

$manifestPath = Join-Path $SourceRoot "FLEET_MANIFEST.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Fleet manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$key = Get-DotEnvValue -Path $RepoEnvFile -Name "CLASSIFIRE_MISSION_CONTROL_API_KEY"
$headers = @{
    Authorization = "Bearer $key"
    "x-api-key" = $key
    "Content-Type" = "application/json"
}

$agentResponse = Invoke-RestMethod `
    -Method Get `
    -Uri "$($MissionControlUrl.TrimEnd('/'))/api/agents?show_hidden=true&limit=200" `
    -Headers $headers

$agents = @($agentResponse.agents)
if (-not $agents) {
    throw "Mission Control returned no agents. Run the CLASSIFIRE bootstrap/sync first."
}

foreach ($spec in $manifest.agents) {
    $agent = $agents | Where-Object { $_.name -eq $spec.id } | Select-Object -First 1
    if (-not $agent) {
        throw "Mission Control agent not found: $($spec.id)"
    }

    $soulPath = Join-Path (Join-Path (Join-Path $SourceRoot "agents") $spec.id) "SOUL.md"
    if (-not (Test-Path -LiteralPath $soulPath)) {
        throw "SOUL file missing: $soulPath"
    }
    $soul = Get-Content -LiteralPath $soulPath -Raw

    # Update the SOUL through the dedicated endpoint.
    $soulBody = @{ soul_content = $soul } | ConvertTo-Json -Depth 8
    Invoke-RestMethod `
        -Method Put `
        -Uri "$($MissionControlUrl.TrimEnd('/'))/api/agents/$($agent.id)/soul" `
        -Headers $headers `
        -Body $soulBody | Out-Null

    # Preserve existing config, but enforce CLASSIFIRE identity/capability metadata.
    $config = @{}
    if ($agent.config) {
        foreach ($property in $agent.config.PSObject.Properties) {
            $config[$property.Name] = $property.Value
        }
    }
    $config["openclawId"] = $spec.id
    $config["framework"] = "OpenClaw"
    $config["capabilities"] = @($spec.capabilities)
    $config["classifireAgentDefinitionVersion"] = $manifest.version
    $config["classifireVisualWorkflowVersion"] = "barrier-opening-service-validator-v1"

    $updateBody = @{
        name = $spec.id
        role = $spec.role
        config = $config
    } | ConvertTo-Json -Depth 20

    Invoke-RestMethod `
        -Method Put `
        -Uri "$($MissionControlUrl.TrimEnd('/'))/api/agents" `
        -Headers $headers `
        -Body $updateBody | Out-Null

    Write-Host "Updated Mission Control agent $($spec.id)" -ForegroundColor Green
}

Write-Host ""
Write-Host "CLASSIFIRE Mission Control agent definitions updated." -ForegroundColor Green
Write-Host "No canonical estimate records were changed." -ForegroundColor Green
