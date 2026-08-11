param(
    [string]$SourceRoot = $PSScriptRoot,

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

function Get-ClassifireMissionControlAgent {
    param(
        [object[]]$Agents,
        [object]$Spec
    )

    $byOpenClawId = @(
        $Agents | Where-Object {
            $_.config -and
            $_.config.openclawId -and
            ([string]$_.config.openclawId -eq [string]$Spec.id)
        }
    )
    if ($byOpenClawId.Count -gt 1) {
        $matches = ($byOpenClawId | ForEach-Object { "id=$($_.id), name=$($_.name)" }) -join "; "
        throw "Mission Control has multiple agents with config.openclawId '$($Spec.id)': $matches"
    }
    if ($byOpenClawId.Count -eq 1) {
        return $byOpenClawId[0]
    }

    $byName = @(
        $Agents | Where-Object {
            ([string]$_.name -eq [string]$Spec.id) -or
            ([string]$_.name -eq [string]$Spec.name)
        }
    )
    if ($byName.Count -gt 1) {
        $matches = ($byName | ForEach-Object { "id=$($_.id), name=$($_.name)" }) -join "; "
        throw "Mission Control has multiple fallback name matches for '$($Spec.id)': $matches"
    }
    if ($byName.Count -eq 1) {
        return $byName[0]
    }

    return $null
}

$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot)
$manifestPath = Join-Path $SourceRoot "FLEET_MANIFEST.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Fleet manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$key = Get-DotEnvValue -Path $RepoEnvFile -Name "CLASSIFIRE_MISSION_CONTROL_API_KEY"
$baseUrl = $MissionControlUrl.TrimEnd("/")
$headers = @{
    Authorization = "Bearer $key"
    "x-api-key" = $key
    "Content-Type" = "application/json"
}

$agentResponse = Invoke-RestMethod `
    -Method Get `
    -Uri "$baseUrl/api/agents?show_hidden=true&limit=200" `
    -Headers $headers

$agents = @($agentResponse.agents)
if (-not $agents) {
    throw "Mission Control returned no agents. Run the CLASSIFIRE bootstrap/OpenClaw sync first."
}

foreach ($spec in $manifest.agents) {
    $agent = Get-ClassifireMissionControlAgent -Agents $agents -Spec $spec
    if (-not $agent) {
        throw "Mission Control agent not found for OpenClaw ID '$($spec.id)'. Run the CLASSIFIRE bootstrap/OpenClaw sync first."
    }

    $soulPath = Join-Path (Join-Path (Join-Path $SourceRoot "agents") $spec.id) "SOUL.md"
    if (-not (Test-Path -LiteralPath $soulPath)) {
        throw "SOUL file missing: $soulPath"
    }
    $soul = Get-Content -LiteralPath $soulPath -Raw -Encoding UTF8

    # Preserve all existing Mission Control config while enforcing canonical
    # CLASSIFIRE identity/capability metadata. The stable lookup key is
    # config.openclawId; the Mission Control display name is deliberately preserved.
    $config = @{}
    if ($agent.config) {
        foreach ($property in $agent.config.PSObject.Properties) {
            $config[$property.Name] = $property.Value
        }
    }
    $config["openclawId"] = [string]$spec.id
    $config["framework"] = "OpenClaw"
    $config["capabilities"] = @($spec.capabilities)
    $config["classifireAgentDefinitionVersion"] = [string]$manifest.version
    $config["classifireVisualWorkflowVersion"] = "barrier-opening-service-validator-v1"
    $config["classifireCanonicalAgentName"] = [string]$spec.name

    # Use Mission Control's normal agent update route. This updates SOUL, role,
    # and config together and avoids the dedicated /soul workspace-write route.
    $updateBody = @{
        name = [string]$agent.name
        role = [string]$spec.role
        soul_content = $soul
        config = $config
    } | ConvertTo-Json -Depth 30 -Compress

    Invoke-RestMethod `
        -Method Put `
        -Uri "$baseUrl/api/agents" `
        -Headers $headers `
        -Body $updateBody | Out-Null

    Write-Host "Updated Mission Control agent '$($agent.name)' for OpenClaw ID $($spec.id)" -ForegroundColor Green
}

# Re-read and fail closed unless every canonical agent can be resolved and carries
# the expected fleet-definition version.
$verifyResponse = Invoke-RestMethod `
    -Method Get `
    -Uri "$baseUrl/api/agents?show_hidden=true&limit=200" `
    -Headers $headers

$verifiedAgents = @($verifyResponse.agents)
foreach ($spec in $manifest.agents) {
    $agent = Get-ClassifireMissionControlAgent -Agents $verifiedAgents -Spec $spec
    if (-not $agent) {
        throw "Post-update verification failed: '$($spec.id)' cannot be resolved in Mission Control."
    }
    if ([string]$agent.config.classifireAgentDefinitionVersion -ne [string]$manifest.version) {
        throw "Post-update verification failed for '$($spec.id)': fleet version is '$($agent.config.classifireAgentDefinitionVersion)'."
    }
    if ([string]$agent.config.openclawId -ne [string]$spec.id) {
        throw "Post-update verification failed for '$($spec.id)': config.openclawId is '$($agent.config.openclawId)'."
    }
}

Write-Host ""
Write-Host "CLASSIFIRE Mission Control Agent Fleet v1.0 metadata and SOUL definitions updated and verified." -ForegroundColor Green
Write-Host "Agents were reconciled by config.openclawId first; no new Mission Control agents were created." -ForegroundColor Green
Write-Host "No canonical CLASSIFIRE estimate records were changed." -ForegroundColor Green
