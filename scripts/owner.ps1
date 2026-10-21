param([ValidateSet('create', 'grant', 'reset')][string]$Task = 'grant')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$commands = @{ create = 'create-owner'; grant = 'grant-owner'; reset = 'reset-password' }
Write-Host 'This manages your local installation. No password is passed in arguments or saved by this script.'
docker compose exec backend python -m app.admin $commands[$Task]
if ($LASTEXITCODE -ne 0) { throw 'Owner account operation did not complete.' }
Write-Host 'Sign out and sign in again to see your current access. Open Owner console for account administration.'
