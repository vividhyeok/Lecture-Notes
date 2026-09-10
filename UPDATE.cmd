@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1"
if errorlevel 1 (
  echo.
  echo Update failed. Check the message above.
)
pause
