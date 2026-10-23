@echo off
cd /d "%~dp0"

if not exist .env (
  echo [ERROR] .env not found. Run install.bat first.
  pause
  exit /b 1
)

start "dc_mom_counter - Python" cmd /k ".venv\Scripts\python -m service.app"
start "dc_mom_counter - Bot" cmd /k "cd bot && npm start"

echo Started two windows. Close both windows to stop the bot.
timeout /t 5 >nul
