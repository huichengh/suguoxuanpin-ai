@echo off
chcp 65001 >nul
title Suguo AI - Install Dependencies

echo ============================================================
echo   Suguo AI - Install Dependencies
echo ============================================================
echo.

REM ---------- Backend ----------
echo [1/2] Installing backend dependencies...
cd /d "%~dp0backend"

if not exist ".venv" (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create venv. Please check Python installation.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Backend dependency installation failed.
    pause
    exit /b 1
)
echo [OK] Backend dependencies installed.

REM ---------- Frontend ----------
echo.
echo [2/2] Installing frontend dependencies...
cd /d "%~dp0frontend"

if not exist "node_modules" (
    call npm install --no-audit --no-fund
    if errorlevel 1 (
        echo [ERROR] Frontend dependency installation failed.
        pause
        exit /b 1
    )
)
echo [OK] Frontend dependencies installed.

echo.
echo ============================================================
echo   Installation complete!
echo.
echo   Next step:
echo     1. Double-click start_backend.bat
echo     2. Double-click start_frontend.bat
echo.
echo   Then visit: http://127.0.0.1:5174
echo   Demo account: admin / admin123
echo ============================================================
pause
