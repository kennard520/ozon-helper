param([int]$Port = 0, [switch]$SkipSync, [switch]$ForceFrontendBuild)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot
# Only the dedicated lite config is loaded; inherited database/server settings cannot override lite mode.
$LiteEnv = Join-Path $RepoRoot '.env.lite.local'
if (Test-Path $LiteEnv) {
    foreach ($line in Get-Content $LiteEnv) {
        if ($line.Trim() -and -not $line.Trim().StartsWith('#')) {
            $parts = $line -split '=', 2
            if ($parts.Count -eq 2) {
                Set-Item -Path "Env:$($parts[0].Trim())" -Value $parts[1].Trim().Trim('"').Trim("'")
            }
        }
    }
}
$env:OZON_LOCAL_LITE = '1'
$LiteData = Join-Path $RepoRoot 'apps/webui/data/lite'
New-Item -ItemType Directory -Force -Path $LiteData | Out-Null
$env:OZON_WEBUI_DB = Join-Path $LiteData 'products.db'
if (-not $SkipSync) {
    python -m uv sync
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency sync failed' }
}
$Frontend = Join-Path $RepoRoot 'apps/webui/frontend'
if ($ForceFrontendBuild -or -not (Test-Path (Join-Path $Frontend 'dist/index.html'))) {
    Push-Location $Frontend
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency install failed' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    } finally { Pop-Location }
}
if ($Port -gt 0) { python -m uv run --package ozon-webui ozon-webui $Port }
else { python -m uv run --package ozon-webui ozon-webui }
if ($LASTEXITCODE -ne 0) { throw 'Local service failed to start' }
