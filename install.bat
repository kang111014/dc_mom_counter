@echo off
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found. Install Node.js 22 LTS from https://nodejs.org/
  pause
  exit /b 1
)

set PY=py -3.12
%PY% --version >nul 2>nul
if errorlevel 1 set PY=python
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.12 from https://www.python.org/
  pause
  exit /b 1
)

echo [1/3] Installing Node.js packages...
pushd bot
call npm install --no-fund --no-audit
if errorlevel 1 (popd & pause & exit /b 1)
popd

echo [2/3] Creating Python environment...
if not exist .venv %PY% -m venv .venv
if errorlevel 1 (pause & exit /b 1)

echo [3/3] Installing Python packages (this can take a while)...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r service\requirements.txt
if errorlevel 1 (pause & exit /b 1)

if not exist .env copy .env.example .env >nul

echo.
echo Done. Open .env with Notepad, fill in DISCORD_TOKEN / GUILD_ID / OWNER_ID, then run start.bat
pause
