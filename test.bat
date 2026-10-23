@echo off
cd /d "%~dp0"
.venv\Scripts\python -m pytest -q service\tests
pause
