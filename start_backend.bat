@echo off
chcp 65001 >nul
title Suguo AI - Backend API

cd /d "%~dp0backend"

echo ============================================================
echo   Suguo AI - Backend Service (FastAPI)
echo   Starting on http://127.0.0.1:8123
echo   API Docs: http://127.0.0.1:8123/docs
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" (
    echo [INFO] Using .venv virtual environment
    ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8123
) else (
    echo [WARN] .venv not found, using system python
    echo [HINT] Run install.bat first, or: python -m pip install -r requirements.txt
    echo.
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8123
)

pause
