@echo off
chcp 65001 >nul
title Suguo AI - Frontend

cd /d "%~dp0frontend"

echo ============================================================
echo   Suguo AI - Frontend (React + TypeScript + Vite)
echo   Starting on http://127.0.0.1:5174
echo ============================================================
echo.

if exist "node_modules" (
    echo [INFO] Dependencies found, starting dev server
    npx vite
) else (
    echo [ERROR] node_modules not found!
    echo [HINT] Run install.bat first, or: npm install
    pause
    exit /b 1
)
