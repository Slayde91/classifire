param(
    [string]$MissionControlUrl = "http://127.0.0.1:3000"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $repoRoot ".env"

function Get-NonEmptyEnvironmentValue {
    param([string]$Name)

    foreach ($scope in @("Process", "User", "Machine")) {
        $value = [Environment]::GetEnvironmentVariable($Name, $scope)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }
    return $null
}

function Convert-SecureStringToPlainText {
    param([Security.SecureString]$SecureValue)

    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Set-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Value
    )

    $lines = @()
    if (Test-Path -LiteralPath $Path) {
        $lines = @(Get-Content -LiteralPath $Path)
    }

    $prefix = "$Name="
    $updated = $false
    $newLines = foreach ($line in $lines) {
        if ($line.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $updated = $true
            "$prefix$Value"
        }
        else {
            $line
        }
    }

    if (-not $updated) {
        $newLines += "$prefix$Value"
    }

    [System.IO.File]::WriteAllLines(
        $Path,
        [string[]]$newLines,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

if (Get-Command git -ErrorAction SilentlyContinue) {
    Push-Location $repoRoot
    try {
        & git check-ignore --quiet .env
        if ($LASTEXITCODE -ne 0) {
            throw "Refusing to write a secret because .env is not ignored by Git in $repoRoot."
        }
    }
    finally {
        Pop-Location
    }
}

$key = Get-NonEmptyEnvironmentValue "CLASSIFIRE_MISSION_CONTROL_API_KEY"
$source = "CLASSIFIRE_MISSION_CONTROL_API_KEY environment variable"

if ([string]::IsNullOrWhiteSpace($key)) {
    $key = Get-NonEmptyEnvironmentValue "MC_API_KEY"
    $source = "MC_API_KEY environment variable"
}

if ([string]::IsNullOrWhiteSpace($key)) {
    $key = Get-NonEmptyEnvironmentValue "QUANTIFIRE_MISSION_CONTROL_API_KEY"
    $source = "legacy QUANTIFIRE_MISSION_CONTROL_API_KEY environment variable"
}

if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host "Mission Control API key was not found in the current environment." -ForegroundColor Yellow
    Write-Host "Open Mission Control -> Settings -> API Key, then paste the key at the secure prompt." -ForegroundColor Yellow
    $secure = Read-Host "Mission Control API key" -AsSecureString
    $key = Convert-SecureStringToPlainText $secure
    $source = "secure prompt"
}

if ([string]::IsNullOrWhiteSpace($key)) {
    throw "Mission Control API key cannot be blank."
}

Set-DotEnvValue -Path $envPath -Name "CLASSIFIRE_MISSION_CONTROL_URL" -Value $MissionControlUrl
Set-DotEnvValue -Path $envPath -Name "CLASSIFIRE_MISSION_CONTROL_API_KEY" -Value $key

Write-Host "Stored CLASSIFIRE Mission Control configuration in the local gitignored .env." -ForegroundColor Green
Write-Host "Credential source: $source" -ForegroundColor DarkGray
Write-Host "The API key value was not printed." -ForegroundColor Green

$key = $null
$secure = $null

Write-Host ""
Write-Host "Next run:" -ForegroundColor Cyan
Write-Host "  classifire mission-control-bootstrap --repo-url https://github.com/Slayde91/classifire"
