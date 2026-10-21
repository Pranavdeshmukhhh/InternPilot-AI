$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
docker compose exec -T backend python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
Write-Host 'Tests passed. No external applications were submitted by the test suite.'
