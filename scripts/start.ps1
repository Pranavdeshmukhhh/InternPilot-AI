param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.env')) { throw 'Run .\scripts\setup.ps1 first.' }
docker compose up --build --detach --wait --wait-timeout 300
if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Run docker compose ps and docker compose logs --tail=100 to inspect the failed service.' }
docker compose exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready',timeout=10)"
if ($LASTEXITCODE -ne 0) { throw 'The API is not ready. Finish catalog backfill before opening the dashboard: docker compose exec backend python -m app.catalog_migrations backfill' }
$port = '3000'
$portMatch = [regex]::Match([System.IO.File]::ReadAllText((Join-Path (Get-Location) '.env')), '(?m)^APP_PORT=(\d+)\r?$')
if ($portMatch.Success) { $port = $portMatch.Groups[1].Value }
$url = 'http://localhost:' + $port
Write-Host "InternPilot AI is available at $url"
if (-not $NoBrowser) { Start-Process $url }
