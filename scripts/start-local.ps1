<#
.SYNOPSIS
Start Hermes Agent locally on Windows (native .venv or Docker Compose dev stack).

.DESCRIPTION
Loads environment variables from .env.local (falling back to .env.example) and starts
either the native FastAPI server using .venv or the Docker dev stack.
#>
param(
    [switch]$Docker
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($Docker) {
    Write-Host "Starting Hermes Agent Docker dev stack..." -ForegroundColor Cyan
    docker compose --env-file docker/env/.env.dev -f docker/docker-compose.dev.yml up --build -d
    Write-Host "Dev stack started at http://127.0.0.1:8080/health" -ForegroundColor Green
    exit 0
}

$EnvFile = Join-Path $RepoRoot ".env.local"
if (-not (Test-Path $EnvFile)) {
    $EnvFile = Join-Path $RepoRoot ".env.example"
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $val = $parts[1].Trim()
        if (-not [string]::IsNullOrEmpty($val) -or -not (Test-Path "Env:\$key")) {
            Set-Item -Path "Env:\$key" -Value $val
        }
    }
}

$env:PYTHONPATH = Join-Path $RepoRoot "src"
$Uvicorn = Join-Path $RepoRoot ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $Uvicorn)) {
    Write-Error "Virtual environment not found at .venv. Run: python -m venv .venv; .\.venv\Scripts\pip install -e '.[dev]'"
}

Write-Host "Starting Hermes Agent on http://$($env:HERMES_HOST):$($env:HERMES_PORT) ..." -ForegroundColor Cyan
& $Uvicorn api.server:serve --factory --host $env:HERMES_HOST --port $env:HERMES_PORT --reload --app-dir (Join-Path $RepoRoot "src")
