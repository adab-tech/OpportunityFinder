@echo off
title OpportunityFinder
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

echo Starting API at http://127.0.0.1:8000
start "OpportunityFinder API" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe run.py"

timeout /t 3 /nobreak > nul
start "" "http://127.0.0.1:8000/"

echo OpportunityFinder is running. API docs: http://127.0.0.1:8000/docs
pause
