[CmdletBinding()]
param(
    [string]$SourceRunId = "20260809-182033",
    [string]$RunId,
    [int]$RunnerTimeoutSeconds = 1200,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:GatewayPort = 18789
$script:GatewayAddress = "127.0.0.1"
$script:CleanupFailures = [System.Collections.Generic.List[string]]::new()

function Add-ClassifirePowerInterop {
    if ("ClassifireWin32Power" -as [type]) {
        return
    }

    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class ClassifireWin32Power
{
    [StructLayout(LayoutKind.Sequential)]
    public struct SYSTEM_POWER_STATUS
    {
        public byte ACLineStatus;
        public byte BatteryFlag;
        public byte BatteryLifePercent;
        public byte SystemStatusFlag;
        public uint BatteryLifeTime;
        public uint BatteryFullLifeTime;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GetSystemPowerStatus(out SYSTEM_POWER_STATUS status);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint executionState);
}
"@
}

function Assert-AcPower {
    Add-ClassifirePowerInterop
    $powerStatus = New-Object ClassifireWin32Power+SYSTEM_POWER_STATUS
    if (-not [ClassifireWin32Power]::GetSystemPowerStatus([ref]$powerStatus)) {
        throw "Unable to determine AC power status. Proposal-only UAT will not start."
    }
    if ($powerStatus.ACLineStatus -ne 1) {
        throw "AC power is not confirmed online. Plug the computer in before starting proposal-only UAT."
    }
}

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$ArgumentList,
        [Parameter(Mandatory)] [string]$Operation
    )

    $null = & $FilePath @ArgumentList 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE."
    }
}

function Get-ActivePowerSchemeGuid {
    $output = & powercfg /getactivescheme 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read the active Windows power scheme."
    }
    $match = [regex]::Match($output, "[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}")
    if (-not $match.Success) {
        throw "Unable to parse the active Windows power scheme GUID."
    }
    return $match.Value
}

function Get-StandbyAcSeconds {
    param([Parameter(Mandatory)] [string]$SchemeGuid)

    $output = & powercfg /query $SchemeGuid SUB_SLEEP STANDBYIDLE 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read the active scheme AC standby timeout."
    }
    $match = [regex]::Match(
        $output,
        "Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)",
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    if (-not $match.Success) {
        throw "Unable to parse the active scheme AC standby timeout."
    }
    return [Convert]::ToUInt32($match.Groups[1].Value, 16)
}

function Set-StandbyAcSeconds {
    param(
        [Parameter(Mandatory)] [string]$SchemeGuid,
        [Parameter(Mandatory)] [UInt32]$Seconds
    )

    Invoke-CheckedNative -FilePath "powercfg" -ArgumentList @(
        "/setacvalueindex", $SchemeGuid, "SUB_SLEEP", "STANDBYIDLE", "$Seconds"
    ) -Operation "Setting AC standby timeout"
    Invoke-CheckedNative -FilePath "powercfg" -ArgumentList @("/S", $SchemeGuid) -Operation "Reapplying active power scheme"

    $verified = Get-StandbyAcSeconds -SchemeGuid $SchemeGuid
    if ($verified -ne $Seconds) {
        throw "AC standby timeout verification failed."
    }
}

function Set-SystemRequired {
    Add-ClassifirePowerInterop
    $result = [ClassifireWin32Power]::SetThreadExecutionState([uint32]0x80000001)
    if ($result -eq 0) {
        throw "Unable to request continuous system-awake execution state."
    }
}

function Clear-SystemRequired {
    Add-ClassifirePowerInterop
    $result = [ClassifireWin32Power]::SetThreadExecutionState([uint32]0x80000000)
    if ($result -eq 0) {
        throw "Unable to clear the continuous system-awake execution state."
    }
}

function Get-EnvironmentSnapshot {
    param([Parameter(Mandatory)] [string]$Name)

    $item = Get-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        Present = $null -ne $item
        Value = if ($null -eq $item) { $null } else { [string]$item.Value }
    }
}

function Restore-EnvironmentSnapshot {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] $Snapshot
    )

    if ($Snapshot.Present) {
        Set-Item -LiteralPath "Env:$Name" -Value $Snapshot.Value
    }
    else {
        Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
    }
}

function New-TemporaryGatewayToken {
    $bytes = [byte[]]::new(32)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Get-LoopbackListenerPid {
    $listeners = @(
        Get-NetTCPConnection -State Listen -LocalAddress $script:GatewayAddress -LocalPort $script:GatewayPort -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    if ($listeners.Count -gt 1) {
        throw "More than one process is listening on the controlled Gateway port."
    }
    if ($listeners.Count -eq 0) {
        return $null
    }
    return [int]$listeners[0]
}

function Wait-ForGatewayListener {
    param(
        [Nullable[int]]$ExpectedPid,
        [Parameter(Mandatory)] [bool]$ShouldListen,
        [int]$TimeoutSeconds = 30
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $listenerPid = Get-LoopbackListenerPid
        if (-not $ShouldListen -and $null -eq $listenerPid) {
            return $true
        }
        if (
            $ShouldListen -and
            $null -ne $listenerPid -and
            ($null -eq $ExpectedPid -or $listenerPid -eq $ExpectedPid)
        ) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    return $false
}

function Invoke-OpenClaw {
    param(
        [Parameter(Mandatory)] [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $null = & $script:NodeExe $script:OpenClawMjs @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "OpenClaw command failed with exit code $exitCode."
    }
    return $exitCode
}

function Test-GatewayRpc {
    $exitCode = Invoke-OpenClaw -Arguments @(
        "gateway", "status", "--require-rpc", "--timeout", "60000"
    ) -AllowFailure
    return $exitCode -eq 0
}

function Write-LaunchReceipt {
    param(
        [Parameter(Mandatory)] [string]$TargetDirectory,
        [Parameter(Mandatory)] [string]$SourceReceiptPath,
        [Parameter(Mandatory)] [string]$FreshRunId,
        [Parameter(Mandatory)] [string]$SchemeGuid,
        [Parameter(Mandatory)] [UInt32]$StandbySeconds
    )

    $payload = [ordered]@{
        schema = "CLASSIFIRE-PROPOSAL-ONLY-SAFE-LAUNCH-v1"
        source_run_id = $SourceRunId
        run_id = $FreshRunId
        source_prepared_receipt_sha256 = (Get-FileHash -LiteralPath $SourceReceiptPath -Algorithm SHA256).Hash
        runner_sha256 = (Get-FileHash -LiteralPath $script:RunnerPath -Algorithm SHA256).Hash
        wrapper_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
        active_power_scheme_guid = $SchemeGuid
        captured_ac_standby_seconds = $StandbySeconds
        gateway_port = $script:GatewayPort
        gateway_host = $script:GatewayAddress
        token_persisted = $false
        canonical_write_mode = "proposal_only"
    }
    $payload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $TargetDirectory "00-proposal-only-safe-launch.json") -Encoding utf8
}

function New-FreshPreparedReceipt {
    param(
        [Parameter(Mandatory)] [string]$SourceReceiptPath,
        [Parameter(Mandatory)] [string]$TargetDirectory,
        [Parameter(Mandatory)] [string]$FreshRunId
    )

    $receipt = Get-Content -LiteralPath $SourceReceiptPath -Raw | ConvertFrom-Json -AsHashtable
    $receipt["run_id"] = $FreshRunId
    $receipt["proposal_only_source_run_id"] = $SourceRunId
    $receipt | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $TargetDirectory "00-prepared.json") -Encoding utf8
}

$root = Split-Path -Parent $PSScriptRoot
$script:RunnerPath = Join-Path $PSScriptRoot "run_classifire_real_uat_fireseals_visualvalidated_proposal_only.py"
$script:PythonExe = Join-Path $root ".venv\Scripts\python.exe"
$script:NodeExe = "C:\Program Files\nodejs\node.exe"
$script:OpenClawMjs = Join-Path $env:APPDATA "npm\node_modules\openclaw\openclaw.mjs"

if ([string]::IsNullOrWhiteSpace($RunId)) {
    $RunId = "{0}-fullres-{1}" -f (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss"), ([Guid]::NewGuid().ToString("N").Substring(0, 8))
}

$sourceReceiptPath = Join-Path $root "data\real-uat\$SourceRunId\00-prepared.json"
$targetDirectory = Join-Path $root "data\real-uat\$RunId"

foreach ($path in @($script:RunnerPath, $script:PythonExe, $script:NodeExe, $script:OpenClawMjs, $sourceReceiptPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required controlled-UAT file is unavailable."
    }
}
if (Test-Path -LiteralPath $targetDirectory) {
    throw "Fresh run namespace already exists; refusing to overwrite receipts."
}
if ($RunnerTimeoutSeconds -lt 1) {
    throw "RunnerTimeoutSeconds must be positive."
}

Assert-AcPower
$schemeGuid = Get-ActivePowerSchemeGuid
$capturedStandbySeconds = Get-StandbyAcSeconds -SchemeGuid $schemeGuid

Write-Host "Controlled proposal-only UAT run ID: $RunId"
Write-Host "Captured AC standby timeout: $capturedStandbySeconds seconds"
Write-Host "Manual recovery if this process is terminated: powercfg /setacvalueindex $schemeGuid SUB_SLEEP STANDBYIDLE $capturedStandbySeconds ; powercfg /S $schemeGuid"

if ($DryRun) {
    Write-Host "PASS dry run: no receipt, power, Gateway, environment, API, or model action was changed."
    exit 0
}

$tokenSnapshot = Get-EnvironmentSnapshot -Name "OPENCLAW_GATEWAY_TOKEN"
$httpUrlSnapshot = Get-EnvironmentSnapshot -Name "OPENCLAW_GATEWAY_HTTP_URL"
$managedGatewayHealthy = $false
$managedStopAttempted = $false
$temporaryGatewayProcess = $null
$temporaryGatewayPid = $null
$sleepSettingChanged = $false
$executionStateSet = $false
$runnerExitCode = 1

try {
    if (-not (Test-GatewayRpc)) {
        throw "Managed OpenClaw Gateway RPC is not healthy; proposal-only UAT will not restart it."
    }
    $managedListenerPid = Get-LoopbackListenerPid
    if ($null -eq $managedListenerPid) {
        throw "Managed OpenClaw Gateway has no verified loopback listener on the controlled port."
    }
    $managedGatewayHealthy = $true

    New-Item -ItemType Directory -Path $targetDirectory -ErrorAction Stop | Out-Null
    New-FreshPreparedReceipt -SourceReceiptPath $sourceReceiptPath -TargetDirectory $targetDirectory -FreshRunId $RunId
    Write-LaunchReceipt -TargetDirectory $targetDirectory -SourceReceiptPath $sourceReceiptPath -FreshRunId $RunId -SchemeGuid $schemeGuid -StandbySeconds $capturedStandbySeconds

    $sleepSettingChanged = $true
    Set-StandbyAcSeconds -SchemeGuid $schemeGuid -Seconds 0
    Set-SystemRequired
    $executionStateSet = $true

    $managedStopAttempted = $true
    Invoke-OpenClaw -Arguments @("gateway", "stop") | Out-Null
    if (-not (Wait-ForGatewayListener -ExpectedPid $null -ShouldListen $false)) {
        throw "Managed Gateway listener did not stop before temporary Gateway launch."
    }

    $env:OPENCLAW_GATEWAY_TOKEN = New-TemporaryGatewayToken
    $env:OPENCLAW_GATEWAY_HTTP_URL = "http://$script:GatewayAddress`:$script:GatewayPort/v1"
    $temporaryGatewayProcess = Start-Process -FilePath $script:NodeExe -ArgumentList @(
        $script:OpenClawMjs, "gateway", "--port", "$script:GatewayPort", "--bind", "loopback", "--auth", "token", "run"
    ) -PassThru -WindowStyle Hidden
    $temporaryGatewayPid = [int]$temporaryGatewayProcess.Id

    if (-not (Wait-ForGatewayListener -ExpectedPid $temporaryGatewayPid -ShouldListen $true)) {
        throw "Temporary Gateway listener identity did not match the captured process ID."
    }
    if (-not (Test-GatewayRpc)) {
        throw "Temporary Gateway authenticated RPC preflight failed."
    }

    & $script:PythonExe $script:RunnerPath --run-id $RunId --timeout-seconds $RunnerTimeoutSeconds
    $runnerExitCode = $LASTEXITCODE
}
catch {
    Write-Error "Controlled proposal-only UAT failed: $($_.Exception.Message)"
    $runnerExitCode = 1
}
finally {
    if ($null -ne $temporaryGatewayPid) {
        try {
            $process = Get-Process -Id $temporaryGatewayPid -ErrorAction SilentlyContinue
            if ($null -ne $process) {
                Stop-Process -Id $temporaryGatewayPid -Force -ErrorAction Stop
                $process.WaitForExit(15000) | Out-Null
            }
        }
        catch {
            $script:CleanupFailures.Add("temporary Gateway stop failed")
        }
    }

    $environmentRestored = $true
    try {
        Restore-EnvironmentSnapshot -Name "OPENCLAW_GATEWAY_TOKEN" -Snapshot $tokenSnapshot
        Restore-EnvironmentSnapshot -Name "OPENCLAW_GATEWAY_HTTP_URL" -Snapshot $httpUrlSnapshot
    }
    catch {
        $environmentRestored = $false
        $script:CleanupFailures.Add("Gateway environment restoration failed")
    }

    if ($sleepSettingChanged) {
        try {
            Set-StandbyAcSeconds -SchemeGuid $schemeGuid -Seconds $capturedStandbySeconds
        }
        catch {
            $script:CleanupFailures.Add("AC standby timeout restoration failed")
        }
    }

    if ($executionStateSet) {
        try {
            Clear-SystemRequired
        }
        catch {
            $script:CleanupFailures.Add("system-awake execution-state cleanup failed")
        }
    }

    if ($managedGatewayHealthy -and $managedStopAttempted) {
        if (-not $environmentRestored) {
            $script:CleanupFailures.Add("managed Gateway was not restarted because its original environment was not restored")
        }
        else {
            try {
                Invoke-OpenClaw -Arguments @("gateway", "start") | Out-Null
                if (-not (Wait-ForGatewayListener -ExpectedPid $null -ShouldListen $true)) {
                    throw "Managed Gateway listener did not return."
                }
                if (-not (Test-GatewayRpc)) {
                    throw "Managed Gateway RPC did not recover."
                }
            }
            catch {
                $script:CleanupFailures.Add("managed Gateway restart or verification failed")
            }
        }
    }
}

if ($runnerExitCode -ne 0) {
    exit $runnerExitCode
}
if ($script:CleanupFailures.Count -gt 0) {
    Write-Error ("Controlled proposal-only UAT cleanup failed: " + ($script:CleanupFailures -join "; "))
    exit 2
}

Write-Host "PASS controlled proposal-only UAT completed and managed state was restored."
exit 0
