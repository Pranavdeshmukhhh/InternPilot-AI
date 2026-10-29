param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
# Docker installs the locked frontend/backend dependencies and runs every service.
# No secrets are printed or written into the source distribution.
& (Join-Path $PSScriptRoot 'setup.ps1') -NoStart
& (Join-Path $PSScriptRoot 'start.ps1') -NoBrowser
docker compose exec -T backend python -c "from app.database import SessionLocal; from app.founder_security import founder_exists; db=SessionLocal(); present=founder_exists(db); db.close(); raise SystemExit(0 if present else 3)"
$founderState = $LASTEXITCODE
if ($founderState -eq 3) {
    Write-Host 'Create your private founder login. Choose your email and password; password entry is hidden.'
    docker compose exec backend python -m app.admin create-owner
    if ($LASTEXITCODE -ne 0) { throw 'Founder setup was not completed. Run docker compose exec backend python -m app.admin create-owner to retry.' }
} elseif ($founderState -ne 0) {
    throw 'Could not verify founder setup. Inspect the backend health before continuing.'
}
$port = '3000'
$match = [regex]::Match([System.IO.File]::ReadAllText((Join-Path $projectRoot '.env')), '(?m)^APP_PORT=(\d+)\r?$')
if ($match.Success) { $port = $match.Groups[1].Value }
$url = 'http://localhost:' + $port + '/login'
Write-Host "Sign in at $url with the founder email and password you chose."
if (-not $NoBrowser) { Start-Process $url }
