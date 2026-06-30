param(
    [int]$Port = 0,
    [switch]$SkipSync,
    [switch]$SkipFrontendBuild,
    [switch]$ForceFrontendBuild,
    [string]$EnvFile = ".env.local"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendDir = Join-Path $RepoRoot "apps\webui\frontend"
$DistIndex = Join-Path $FrontendDir "dist\index.html"
$EnvPath = Join-Path $RepoRoot $EnvFile

function Run-Step {
    param(
        [string]$Title,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Title" -ForegroundColor Cyan
    & $Command
}

Set-Location $RepoRoot

if (Test-Path $EnvPath) {
    Write-Host "Loading local env file: $EnvPath" -ForegroundColor Green
    Get-Content $EnvPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            return
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found in PATH. Install Python 3.10+ or open a shell where python is available."
}

if (-not $SkipSync) {
    Run-Step "Sync Python dependencies" {
        python -m uv sync
    }
}

$ShouldBuildFrontend = $ForceFrontendBuild -or (-not (Test-Path $DistIndex))
if (-not $SkipFrontendBuild -and $ShouldBuildFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm was not found in PATH. Install Node.js, or run with -SkipFrontendBuild if frontend/dist already exists."
    }

    Run-Step "Install frontend dependencies" {
        Push-Location $FrontendDir
        try {
            if (Test-Path (Join-Path $FrontendDir "package-lock.json")) {
                npm install
            } else {
                npm install
            }
        } finally {
            Pop-Location
        }
    }

    Run-Step "Build frontend assets for FastAPI" {
        Push-Location $FrontendDir
        try {
            npm run build
        } finally {
            Pop-Location
        }
    }
} elseif ($SkipFrontendBuild) {
    Write-Host "Skipping frontend build." -ForegroundColor Yellow
} else {
    Write-Host "Frontend dist already exists. Use -ForceFrontendBuild to rebuild it." -ForegroundColor Green
}

Run-Step "Start Ozon WebUI" {
    if ($Port -gt 0) {
        python -m uv run --package ozon-webui ozon-webui $Port
    } else {
        python -m uv run --package ozon-webui ozon-webui
    }
}
