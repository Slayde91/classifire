[CmdletBinding()]
param(
    [string]$Owner = "Slayde91",
    [string]$Repository = "quantifire",
    [ValidateSet("private", "public", "internal")]
    [string]$Visibility = "private",
    [string]$CommitMessage = "Initial QUANTIFIRE pre-production integration build"
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# The script may be saved in either the repository root or its scripts folder.
$CandidateRoot = Split-Path -Path $PSScriptRoot -Parent
if (Test-Path (Join-Path $PSScriptRoot "pyproject.toml")) {
    $RepositoryRoot = $PSScriptRoot
} elseif (Test-Path (Join-Path $CandidateRoot "pyproject.toml")) {
    $RepositoryRoot = $CandidateRoot
} else {
    throw "Could not locate the QUANTIFIRE repository root. Save this file in the repository root or its scripts folder."
}
Set-Location $RepositoryRoot

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

# Run a native command that is allowed to return a non-zero exit code without
# PowerShell converting its stderr output into a terminating NativeCommandError.
function Test-NativeCommand {
    param([Parameter(Mandatory = $true)][scriptblock]$Command)

    $PreviousErrorActionPreference = $ErrorActionPreference
    $HasNativePreference = Test-Path Variable:PSNativeCommandUseErrorActionPreference
    if ($HasNativePreference) {
        $PreviousNativePreference = $PSNativeCommandUseErrorActionPreference
    }

    try {
        $ErrorActionPreference = "SilentlyContinue"
        if ($HasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $false
        }

        & $Command *> $null
        return ($LASTEXITCODE -eq 0)
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
        if ($HasNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $PreviousNativePreference
        }
    }
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $Name @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE: $Name $($Arguments -join ' ')"
    }
}

Require-Command "git"
Require-Command "gh"

Write-Host "Checking GitHub authentication..."
Invoke-NativeCommand -Name "gh" -Arguments @("auth", "status")

$InsideGitRepository = Test-NativeCommand { & git rev-parse --is-inside-work-tree }
if (-not $InsideGitRepository) {
    Write-Host "Initialising the local Git repository..."
    Invoke-NativeCommand -Name "git" -Arguments @("init", "-b", "main")
}

# Ensure the default local branch is main.
$CurrentBranch = (& git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to determine the current Git branch."
}
if ($CurrentBranch -and $CurrentBranch -ne "main") {
    Invoke-NativeCommand -Name "git" -Arguments @("branch", "-M", "main")
}

# Stage and commit any uncommitted package files.
Invoke-NativeCommand -Name "git" -Arguments @("add", "-A")
$HasStagedChanges = -not (Test-NativeCommand { & git diff --cached --quiet })
$HasHeadCommit = Test-NativeCommand { & git rev-parse --verify HEAD }

if ($HasStagedChanges -or -not $HasHeadCommit) {
    Write-Host "Creating the local commit..."
    Invoke-NativeCommand -Name "git" -Arguments @("commit", "-m", $CommitMessage)
}

$FullRepositoryName = "$Owner/$Repository"
$RemoteUrl = "https://github.com/$FullRepositoryName.git"

Write-Host "Checking whether $FullRepositoryName already exists..."
$RepositoryExists = Test-NativeCommand {
    & gh repo view $FullRepositoryName --json nameWithOwner
}

$OriginExists = Test-NativeCommand { & git remote get-url origin }

if ($RepositoryExists) {
    Write-Host "Repository already exists. Pushing the local main branch..."
    if ($OriginExists) {
        Invoke-NativeCommand -Name "git" -Arguments @("remote", "set-url", "origin", $RemoteUrl)
    }
    else {
        Invoke-NativeCommand -Name "git" -Arguments @("remote", "add", "origin", $RemoteUrl)
    }

    Invoke-NativeCommand -Name "git" -Arguments @("push", "-u", "origin", "main")
}
else {
    Write-Host "Repository does not exist. Creating it as $Visibility and pushing main..."

    # gh repo create cannot add an origin remote when one already exists.
    if ($OriginExists) {
        Invoke-NativeCommand -Name "git" -Arguments @("remote", "remove", "origin")
    }

    Invoke-NativeCommand -Name "gh" -Arguments @(
        "repo", "create", $FullRepositoryName,
        "--$Visibility",
        "--source", ".",
        "--remote", "origin",
        "--push"
    )
}

Write-Host ""
Write-Host "QUANTIFIRE was published successfully:" -ForegroundColor Green
Write-Host "https://github.com/$FullRepositoryName"
