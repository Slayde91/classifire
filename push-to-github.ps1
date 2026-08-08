param(
  [string]$Owner = "Slayde91",
  [string]$Repository = "quantifire",
  [ValidateSet("private", "public", "internal")]
  [string]$Visibility = "private"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "Git is required."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI (gh) is required. Install it from https://cli.github.com/"
}
if (-not (Test-Path .git)) {
  git init -b main
  git config user.name "QUANTIFIRE Publisher"
  git config user.email "slayde@ceasefire.com.au"
  git add -A
  git commit -m "Initial QUANTIFIRE development preview"
}
try { gh auth status | Out-Null } catch { gh auth login }
$full = "$Owner/$Repository"
$exists = $true
try { gh repo view $full | Out-Null } catch { $exists = $false }
if ($exists) {
  git remote remove origin 2>$null
  if ($LASTEXITCODE -ne 0) { $global:LASTEXITCODE = 0 }
  git remote add origin "https://github.com/$full.git"
  git push -u origin main
} else {
  gh repo create $full "--$Visibility" --source . --remote origin --push
}
