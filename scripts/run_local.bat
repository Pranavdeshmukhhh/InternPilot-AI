@echo off
setlocal
title InternPilot AI - Verified Local Startup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0quickstart.ps1"
if errorlevel 1 (
  echo Startup failed. Review the error above. No success is assumed.
  pause
  exit /b 1
)
endlocal
