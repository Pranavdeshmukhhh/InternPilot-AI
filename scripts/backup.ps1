param([string]$Destination = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not $Destination) { $Destination = Join-Path $projectRoot ('backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$Destination = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
Write-Host 'Stopping worker and API briefly to make a consistent backup.'
docker compose stop worker backend
if ($LASTEXITCODE -ne 0) { throw 'Could not stop application services; no backup was attempted.' }
try {
    # Send shell code through stdin so Windows PowerShell 5.1 does not strip
    # embedded quotes while constructing native process arguments.
    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/internpilot-backup.dump' | docker compose exec -T postgres sh
    if ($LASTEXITCODE -ne 0) { throw 'Database backup failed.' }
    docker compose cp postgres:/tmp/internpilot-backup.dump (Join-Path $Destination 'postgres.dump')
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy database backup.' }
    docker compose exec -T postgres rm -f /tmp/internpilot-backup.dump
    # A one-off process uses the existing image and /data volume; no new service is exposed.
    docker compose run --rm --no-deps backend tar --exclude=.backup.tar.gz -czf /data/.backup.tar.gz -C / data
    if ($LASTEXITCODE -ne 0) { throw 'Encrypted file backup failed.' }
    # Use the stopped backend container to copy from its persistent volume.
    docker compose cp backend:/data/.backup.tar.gz (Join-Path $Destination 'app-data.tar.gz')
    if ($LASTEXITCODE -ne 0) { throw 'Could not copy encrypted file backup.' }
    docker compose run --rm --no-deps backend rm -f /data/.backup.tar.gz
    Write-Host "Backup saved to $Destination"
    Write-Host 'Store it securely. Back up ENCRYPTION_KEY separately in encrypted storage. This script does not copy .env.'
} finally {
    docker compose start backend worker
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Could not restart services. Run .\scripts\start.ps1.' }
}
