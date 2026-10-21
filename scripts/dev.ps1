param([ValidateSet('setup', 'api', 'worker', 'web', 'test')][string]$Task = 'setup')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$python = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
if ($Task -eq 'setup') {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 and the Windows Python launcher.' }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 LTS.' }
    py -3.12 -m venv backend\.venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python 3.12 environment.' }
    & $python -m pip install -r backend\requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    & $python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw 'Chromium installation failed.' }
    & $python scripts\setup_env.py
    if ($LASTEXITCODE -ne 0) { throw 'Environment setup failed.' }
    Set-Location frontend
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    Write-Host 'Setup complete. Open three terminals and run dev.ps1 -Task api, worker, and web.'
    exit 0
}
if (-not (Test-Path $python)) { throw 'Run .\scripts\dev.ps1 -Task setup first.' }
switch ($Task) {
    'api' { Set-Location backend; & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload }
    'worker' { Set-Location backend; & $python -m app.worker }
    'web' { Set-Location frontend; npm run dev -- --hostname 127.0.0.1 }
    'test' { Set-Location backend; & $python -m pytest -q }
}
if ($LASTEXITCODE -ne 0) { throw "$Task exited unsuccessfully." }
