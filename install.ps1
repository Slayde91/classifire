$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Invoke-InstallerStep {
    param(
        [string]$Step,
        [string]$Command,
        [string[]]$Arguments
    )

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE. Installation stopped."
    }
}

$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { throw "Python 3.11 or later is required." }

if (-not (Test-Path ".venv")) {
    Invoke-InstallerStep -Step "Create virtual environment" -Command $python -Arguments @("-m", "venv", ".venv")
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
Invoke-InstallerStep -Step "Check Python version" -Command $venvPython -Arguments @("-c", "import sys; assert sys.version_info >= (3, 11), 'QUANTIFIRE requires Python 3.11 or later.'")
Invoke-InstallerStep -Step "Update package tools" -Command $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools")
Invoke-InstallerStep -Step "Install application" -Command $venvPython -Arguments @("-m", "pip", "install", "--no-build-isolation", "-e", ".")

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Change the secret key and administrator settings before production use." -ForegroundColor Yellow
}

Invoke-InstallerStep -Step "Initialize local database" -Command (Join-Path $PSScriptRoot ".venv\Scripts\classifire.exe") -Arguments @("init")

Write-Host ""
Write-Host "QUANTIFIRE installed." -ForegroundColor Green
Write-Host "Activate: .\.venv\Scripts\Activate.ps1"
Write-Host "Create admin: classifire create-admin"
Write-Host "Start: classifire start"
