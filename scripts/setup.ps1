param([switch]$NoStart, [switch]$TestMode)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function New-RandomBytes([int]$Count) {
    $bytes = New-Object byte[] $Count
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return ,$bytes
}
function New-HexSecret {
    return [System.BitConverter]::ToString((New-RandomBytes 32)).Replace('-', '').ToLowerInvariant()
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop for Windows with WSL 2 and Linux containers, then run this script again.'
}
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not running or its Linux engine is unavailable.' }
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required.' }

$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path $envPath)) { Copy-Item (Join-Path $projectRoot '.env.example') $envPath }
$envText = [System.IO.File]::ReadAllText($envPath)
$newSecrets = @{
    ENCRYPTION_KEY = ([System.Convert]::ToBase64String((New-RandomBytes 32))).Replace('+', '-').Replace('/', '_')
    POSTGRES_PASSWORD = New-HexSecret
    REDIS_PASSWORD = New-HexSecret
}
foreach ($name in $newSecrets.Keys) {
    $pattern = '(?m)^' + [regex]::Escape($name) + '=([^\r\n]*)\r?$'
    $match = [regex]::Match($envText, $pattern)
    if (-not $match.Success) {
        $envText += "`n$name=$($newSecrets[$name])`n"
    } elseif ([string]::IsNullOrWhiteSpace($match.Groups[1].Value)) {
        $replacement = $name + '=' + $newSecrets[$name]
        $envText = [regex]::Replace($envText, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $replacement })
    }
}
if ($TestMode) { $envText = [regex]::Replace($envText, '(?m)^TEST_MODE=.*$', 'TEST_MODE=true') }
[System.IO.File]::WriteAllText($envPath, $envText, (New-Object System.Text.UTF8Encoding $false))

# Restrict the local secrets file to the current Windows user when NTFS supports it.
if ($env:OS -eq 'Windows_NT') {
    $account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    icacls $envPath /inheritance:r /grant:r "${account}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Could not restrict .env permissions. Restrict access to this file manually.' }
}
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed validation.' }
Write-Host 'Configuration is ready. Secrets were generated without printing them.'
Write-Host 'Keep a separate encrypted backup of ENCRYPTION_KEY. Losing it makes stored candidate data unreadable.'
if (-not $NoStart) { & (Join-Path $PSScriptRoot 'start.ps1') }
