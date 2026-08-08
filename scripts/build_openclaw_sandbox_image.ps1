param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$docker = Get-Command docker -ErrorAction Stop
$image = "openclaw-sandbox:bookworm-slim"

Write-Host "Checking Docker daemon..." -ForegroundColor Cyan
& $docker.Source info | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon is not reachable. Start Docker Desktop and confirm 'docker info' succeeds."
}

# Do not use `docker image inspect` to test existence here. On Windows PowerShell
# with ErrorActionPreference=Stop, Docker's expected "No such image" stderr can
# become a terminating NativeCommandError before we get a chance to inspect
# LASTEXITCODE. `docker image ls -q <tag>` returns success with empty output when
# the image is absent, which is the behavior we want for an existence probe.
$imageId = (& $docker.Source image ls -q $image 2>$null | Select-Object -First 1 | Out-String).Trim()
$imageExists = -not [string]::IsNullOrWhiteSpace($imageId)

if ($imageExists -and -not $Force) {
    Write-Host "$image already exists. Nothing to build." -ForegroundColor Green
    & $docker.Source image inspect $image --format "{{.Id}}  {{.Created}}" | Out-Host
    exit 0
}

if ($imageExists -and $Force) {
    Write-Host "$image already exists, but -Force was requested. Rebuilding it." -ForegroundColor DarkYellow
}
else {
    Write-Host "$image is not present. Building it now." -ForegroundColor Yellow
}

$tempDir = Join-Path $env:TEMP ("classifire-openclaw-sandbox-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$dockerfile = Join-Path $tempDir "Dockerfile"

$dockerfileContent = @'
FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git jq python3 ripgrep \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox
CMD ["sleep", "infinity"]
'@

[System.IO.File]::WriteAllText(
    $dockerfile,
    $dockerfileContent,
    (New-Object System.Text.UTF8Encoding($false))
)

try {
    Write-Host "Building $image using the OpenClaw documented npm-install sandbox recipe..." -ForegroundColor Cyan
    & $docker.Source build --pull -t $image -f $dockerfile $tempDir
    if ($LASTEXITCODE -ne 0) {
        throw "Docker failed to build $image."
    }

    Write-Host "Verifying sandbox image..." -ForegroundColor Cyan
    & $docker.Source image inspect $image --format "{{.Id}}  {{.Created}}" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Sandbox image build completed but image verification failed."
    }

    Write-Host "Verifying required runtime tools..." -ForegroundColor Cyan
    & $docker.Source run --rm $image sh -lc "python3 --version && bash --version | head -n 1 && command -v jq && command -v rg"
    if ($LASTEXITCODE -ne 0) {
        throw "Sandbox image is missing one or more required runtime tools."
    }

    Write-Host "OpenClaw sandbox image is ready: $image" -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
