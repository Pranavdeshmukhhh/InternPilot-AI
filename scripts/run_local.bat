@echo off
title InternPilot AI - Local Runner
echo Starting InternPilot AI Backend on http://127.0.0.1:8000 ...
start "InternPilot Backend" /min cmd /c "cd /d %~dp0..\backend && ..\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting InternPilot AI Frontend on http://localhost:3000 ...
start "InternPilot Frontend" /min cmd /c "cd /d %~dp0..\frontend && npm.cmd run dev"

timeout /t 3 /nobreak >nul
start http://localhost:3000
echo InternPilot AI is running in the background!
