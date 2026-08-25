$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { throw "Python 3.11 or later is required." }

if (-not (Test-Path ".venv")) {
    & $python -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $venvPython -c "import sys; assert sys.version_info >= (3, 11), 'QUANTIFIRE requires Python 3.11 or later.'"
& $venvPython -m pip install --upgrade pip setuptools
& $venvPython -m pip install --no-build-isolation -e .

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from the local-development example. Review it before running CLASSIFIRE." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "QUANTIFIRE installed." -ForegroundColor Green
Write-Host "No database seed or administrator account was created." -ForegroundColor Yellow
Write-Host "Activate: .\.venv\Scripts\Activate.ps1"
Write-Host "Review: .env"
Write-Host '1. Create admin: classifire create-admin --email "admin@your-company.example" --operator-reference "initial-admin-provisioning"'
Write-Host '2. Initialise: classifire init --administrator-email "admin@your-company.example" --operator-reference "initial-database-bootstrap"'
Write-Host "3. Start: classifire start"
Write-Host "Production requirements: docs\PRODUCTION_CONFIGURATION.md"
