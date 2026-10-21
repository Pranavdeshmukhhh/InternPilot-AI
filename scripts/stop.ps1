$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
docker compose stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop all services.' }
Write-Host 'Services stopped. Database and encrypted documents remain in Docker volumes.'
