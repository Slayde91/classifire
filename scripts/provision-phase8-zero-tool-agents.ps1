[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$VerifyLive,
    [string]$WorkspaceRoot = "C:\CLASSIFIRE-OpenClaw",
    [string]$OpenClawHome = (Join-Path $env:USERPROFILE ".openclaw")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Path $PSScriptRoot -Parent
$ManifestPath = Join-Path $RepositoryRoot "config\phase8-zero-tool-agents.json"
$BootstrapPath = Join-Path $RepositoryRoot "config\phase8-zero-tool-workspace\AGENTS.md"

function Invoke-OpenClawJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $NativeArguments = @()
    $EscapeJson = $false
    foreach ($Argument in $Arguments) {
        if ($EscapeJson) {
            $EscapedQuote = [string][char]92 + [string][char]34
            $NativeArguments += $Argument.Replace([string][char]34, $EscapedQuote)
            $EscapeJson = $false
        }
        else {
            $NativeArguments += $Argument
            $EscapeJson = ($Argument -eq "--params")
        }
    }
    $Output = & openclaw @NativeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw command failed safely. No prompt or evidence was sent."
    }
    return ($Output | Out-String | ConvertFrom-Json)
}

function Get-PropertyNames {
    param([Parameter(Mandatory = $true)]$Value)
    return @($Value.PSObject.Properties.Name | Sort-Object)
}

function Test-ExactNames {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string[]]$Names
    )
    return ((Get-PropertyNames $Value) -join "|") -eq (($Names | Sort-Object) -join "|")
}

function Test-AgentPolicy {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]$Expected
    )

    if ($Actual.id -ne $Expected.id -or
        $Actual.workspace -ne $Expected.workspace -or
        $Actual.agentDir -ne $Expected.agentDir -or
        -not (Test-ExactNames $Actual.tools @("profile", "deny", "elevated")) -or
        $Actual.tools.profile -ne "minimal" -or
        @($Actual.tools.deny).Count -ne 1 -or
        @($Actual.tools.deny)[0] -ne "*" -or
        -not (Test-ExactNames $Actual.tools.elevated @("enabled")) -or
        $Actual.tools.elevated.enabled -ne $false -or
        -not (Test-ExactNames $Actual.sandbox @("mode", "backend", "workspaceAccess", "scope")) -or
        $Actual.sandbox.mode -ne "all" -or
        $Actual.sandbox.backend -ne "docker" -or
        $Actual.sandbox.workspaceAccess -ne "none" -or
        $Actual.sandbox.scope -ne "agent") {
        return $false
    }

    $ActualModel = $Actual.models.PSObject.Properties[$Expected.model]
    return ($null -ne $ActualModel -and
        $ActualModel.Value.agentRuntime.id -eq "openclaw")
}

if (-not (Get-Command openclaw -ErrorAction SilentlyContinue)) {
    throw "OpenClaw was not found in PATH."
}
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $BootstrapPath -PathType Leaf)) {
    throw "The checked-in Phase 8 zero-tool profile assets are incomplete."
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.schema -ne "classifire.phase8-zero-tool-agents.v1" -or
    @($Manifest.agents).Count -ne 2) {
    throw "The Phase 8 zero-tool profile manifest is invalid."
}

$VersionOutput = (& openclaw --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $VersionOutput -notmatch [regex]::Escape($Manifest.openclaw_version)) {
    throw "The installed OpenClaw version does not match the reviewed profile version."
}

$DesiredAgents = @()
foreach ($Definition in $Manifest.agents) {
    if ($Definition.id -notmatch '^[a-z0-9][a-z0-9_-]{0,63}$') {
        throw "The Phase 8 zero-tool profile manifest contains an invalid agent id."
    }
    $Workspace = Join-Path $WorkspaceRoot $Definition.id
    $AgentDirectory = Join-Path (Join-Path $OpenClawHome "agents") "$($Definition.id)\agent"
    $ModelPolicy = [ordered]@{}
    $ModelPolicy[$Manifest.model] = [ordered]@{
        agentRuntime = [ordered]@{ id = "openclaw" }
    }
    $DesiredAgents += [pscustomobject][ordered]@{
        id = $Definition.id
        name = $Definition.id
        workspace = $Workspace
        agentDir = $AgentDirectory
        models = [pscustomobject]$ModelPolicy
        identity = [pscustomobject][ordered]@{
            name = $Definition.name
            theme = $Definition.theme
        }
        sandbox = [pscustomobject][ordered]@{
            mode = "all"
            backend = "docker"
            workspaceAccess = "none"
            scope = "agent"
        }
        tools = [pscustomobject][ordered]@{
            profile = "minimal"
            deny = @("*")
            elevated = [pscustomobject][ordered]@{ enabled = $false }
        }
        model = $Manifest.model
    }
}

$ConfiguredAgents = @(Invoke-OpenClawJson @("config", "get", "agents.list", "--json"))
$MissingAgents = @()
foreach ($Expected in $DesiredAgents) {
    $Matches = @($ConfiguredAgents | Where-Object { $_.id -eq $Expected.id })
    if ($Matches.Count -gt 1) {
        throw "Duplicate configured identity detected for $($Expected.id)."
    }
    if ($Matches.Count -eq 1) {
        if (-not (Test-AgentPolicy $Matches[0] $Expected)) {
            throw "Existing identity $($Expected.id) conflicts with the reviewed zero-tool policy."
        }
        Write-Host "Verified configured policy: $($Expected.id)"
    }
    else {
        $MissingAgents += $Expected
        Write-Host "Planned zero-tool identity: $($Expected.id)"
    }
}

if ($MissingAgents.Count -gt 0) {
    $BatchOperations = @()
    $NextIndex = $ConfiguredAgents.Count
    foreach ($Expected in $MissingAgents) {
        $Entry = [ordered]@{}
        foreach ($Property in $Expected.PSObject.Properties) {
            if ($Property.Name -ne "model") {
                $Entry[$Property.Name] = $Property.Value
            }
        }
        $BatchOperations += [pscustomobject][ordered]@{
            path = "agents.list[$NextIndex]"
            value = [pscustomobject]$Entry
        }
        $NextIndex += 1
    }

    if ($BatchOperations.Count -gt 0) {
        $BatchPath = Join-Path ([System.IO.Path]::GetTempPath()) (
            "classifire-phase8-zero-tool-$([guid]::NewGuid().ToString('N')).json"
        )
        $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        try {
            $BatchJson = $BatchOperations | ConvertTo-Json -Depth 12
            [System.IO.File]::WriteAllText($BatchPath, $BatchJson, $Utf8NoBom)
            & openclaw config set --batch-file $BatchPath --dry-run | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "OpenClaw rejected the reviewed profiles during dry-run."
            }

            if ($Apply) {
                foreach ($Expected in $MissingAgents) {
                    $Destination = Join-Path $Expected.workspace "AGENTS.md"
                    if (Test-Path -LiteralPath $Destination) {
                        $ExistingHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
                        $ExpectedHash = (Get-FileHash -LiteralPath $BootstrapPath -Algorithm SHA256).Hash
                        if ($ExistingHash -ne $ExpectedHash) {
                            throw "Workspace bootstrap conflict detected for $($Expected.id)."
                        }
                    }
                }

                foreach ($Expected in $MissingAgents) {
                    New-Item -ItemType Directory -Path $Expected.workspace -Force | Out-Null
                    New-Item -ItemType Directory -Path $Expected.agentDir -Force | Out-Null
                    $Destination = Join-Path $Expected.workspace "AGENTS.md"
                    if (-not (Test-Path -LiteralPath $Destination)) {
                        Copy-Item -LiteralPath $BootstrapPath -Destination $Destination
                    }
                }

                & openclaw config set --batch-file $BatchPath | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "OpenClaw failed while installing the reviewed profiles."
                }
            }
        }
        finally {
            if (Test-Path -LiteralPath $BatchPath) {
                Remove-Item -LiteralPath $BatchPath -Force
            }
        }
        if ($Apply) {
            foreach ($Expected in $MissingAgents) {
                Write-Host "Installed zero-tool identity: $($Expected.id)"
            }
        }
    }
}

if ($Apply) {
    & openclaw config validate --json | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw configuration validation failed after installation."
    }
}
if (-not $Apply -and $MissingAgents.Count -gt 0) {
    Write-Host "Plan only. Re-run with -Apply after review."
}

if ($VerifyLive) {
    if ($MissingAgents.Count -gt 0 -and -not $Apply) {
        throw "Live verification requires the reviewed identities to be installed first."
    }
    foreach ($Expected in $DesiredAgents) {
        $SessionKey = "agent:$($Expected.id):classifire-phase8-profile-proof-$([guid]::NewGuid().ToString('N'))"
        $Created = Invoke-OpenClawJson @(
            "gateway", "call", "sessions.create", "--params",
            (@{ key = $SessionKey; agentId = $Expected.id; model = $Expected.model } | ConvertTo-Json -Compress),
            "--timeout", "10000", "--json"
        )
        if ($Created.ok -ne $true -or $Created.runStarted -ne $false) {
            throw "Metadata-only session creation failed safely for $($Expected.id)."
        }
        $Described = Invoke-OpenClawJson @(
            "gateway", "call", "sessions.describe", "--params",
            (@{ key = $SessionKey } | ConvertTo-Json -Compress),
            "--timeout", "10000", "--json"
        )
        $ModelParts = @($Expected.model -split '/', 2)
        if ($null -eq $Described.session -or
            $Described.session.key -ne $SessionKey -or
            $Described.session.modelProvider -ne $ModelParts[0] -or
            $Described.session.model -ne $ModelParts[1]) {
            throw "Live model identity verification failed safely for $($Expected.id)."
        }
        $Inventory = Invoke-OpenClawJson @(
            "gateway", "call", "tools.effective", "--params",
            (@{ sessionKey = $SessionKey; agentId = $Expected.id } | ConvertTo-Json -Compress),
            "--timeout", "10000", "--json"
        )
        $EffectiveTools = @(
            foreach ($Group in @($Inventory.groups)) {
                foreach ($Tool in @($Group.tools)) { $Tool.id }
            }
        )
        if ($EffectiveTools.Count -ne 0) {
            throw "Live zero-tool verification failed safely for $($Expected.id)."
        }
        Write-Host "LIVE EMPTY TOOL INVENTORY VERIFIED: $($Expected.id)"
    }
}

Write-Host "No prompt, image, provider request, canonical write, or lock was performed."
