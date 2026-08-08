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
    Write-Host "Created .env from .env.example. Change the secret key and administrator settings before production use." -ForegroundColor Yellow
}

& (Join-Path $PSScriptRoot ".venv\Scripts\classifire.exe") init

Write-Host ""
Write-Host "QUANTIFIRE installed." -ForegroundColor Green
Write-Host "Activate: .\.venv\Scripts\Activate.ps1"
Write-Host "Create admin: quantifire create-admin"
Write-Host "Start: quantifire start"
