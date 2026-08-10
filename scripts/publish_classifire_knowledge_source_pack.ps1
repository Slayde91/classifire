param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePackPath,

    [switch]$CommitAndPush
)

$ErrorActionPreference = 'Stop'

$ExpectedSha256 = '75cccd7a33b84b276bbc47820f204b020151553d410dad73cc0d39c2ce2f925e'
$ExpectedSize = 7514016
$ExpectedFileCount = 16
$DestinationRelative = 'knowledge/source/CLASSIFIRE_Knowledge_Source_Pack_v2.13.zip'
$RequiredBranch = 'feature/classifire-product-rename'

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found."
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $RepoRoot

Assert-Command 'git'
if (-not (Test-Path -LiteralPath $SourcePackPath -PathType Leaf)) {
    throw "Knowledge source pack not found: $SourcePackPath"
}

$Branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $Branch -ne $RequiredBranch) {
    throw "Publish only from branch '$RequiredBranch'. Current branch: '$Branch'."
}

$RepoVisibility = 'private'
$Remote = (git remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $Remote -notmatch 'Slayde91/classifire') {
    throw "Unexpected Git remote. Expected Slayde91/classifire; got '$Remote'."
}

$SourceItem = Get-Item -LiteralPath $SourcePackPath
if ($SourceItem.Length -ne $ExpectedSize) {
    throw "Knowledge source pack size mismatch: $($SourceItem.Length) != $ExpectedSize bytes."
}
$ActualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $SourceItem.FullName).Hash.ToLowerInvariant()
if ($ActualSha -ne $ExpectedSha256) {
    throw "Knowledge source pack SHA-256 mismatch: $ActualSha != $ExpectedSha256."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [System.IO.Compression.ZipFile]::OpenRead($SourceItem.FullName)
try {
    $Entries = @($Archive.Entries | Where-Object { -not [string]::IsNullOrWhiteSpace($_.Name) })
    if ($Entries.Count -ne $ExpectedFileCount) {
        throw "Knowledge source pack entry count mismatch: $($Entries.Count) != $ExpectedFileCount."
    }
    foreach ($Entry in $Entries) {
        if (-not $Entry.FullName.StartsWith('knowledge/source/CLASSIFIRE_')) {
            throw "Unexpected archive path: $($Entry.FullName)"
        }
    }
}
finally {
    $Archive.Dispose()
}

$Destination = Join-Path $RepoRoot $DestinationRelative
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
Copy-Item -LiteralPath $SourceItem.FullName -Destination $Destination -Force

# The repository deliberately ignores knowledge/source/** for ordinary work, but
# *.zip is LFS-tracked. This publisher is the explicit controlled exception: it
# force-adds only the verified governed source pack and requires Git LFS.
try {
    git lfs version | Out-Null
}
catch {
    throw "Git LFS is required to publish the controlled knowledge source pack. Install Git LFS, then rerun."
}
if ($LASTEXITCODE -ne 0) {
    throw "Git LFS is required to publish the controlled knowledge source pack."
}

git lfs install --local | Out-Null
git add -f -- $DestinationRelative
if ($LASTEXITCODE -ne 0) {
    throw "git add failed for $DestinationRelative"
}

$PointerCheck = git check-attr filter -- $DestinationRelative
if ($LASTEXITCODE -ne 0 -or $PointerCheck -notmatch 'filter: lfs') {
    throw "The knowledge source pack is not covered by Git LFS attributes."
}

Write-Host 'PASS governed knowledge source pack verified.'
Write-Host "PASS SHA-256 $ActualSha"
Write-Host "PASS archive entries $ExpectedFileCount"
Write-Host "PASS staged through Git LFS at $DestinationRelative"
Write-Host "Repository visibility requirement: $RepoVisibility"

if ($CommitAndPush) {
    git commit -m 'Publish governed CLASSIFIRE v2.13 knowledge source pack'
    if ($LASTEXITCODE -ne 0) {
        throw 'git commit failed.'
    }
    git push origin $RequiredBranch
    if ($LASTEXITCODE -ne 0) {
        throw 'git push failed.'
    }
    Write-Host 'PASS private GitHub knowledge source publication pushed.'
}
else {
    Write-Host 'Source pack is staged only. Review git status, then rerun with -CommitAndPush when ready.'
}
