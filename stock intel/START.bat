@echo off
title DericBI Stock Intelligence
color 0B
cls

echo.
echo  ================================================
echo    DericBI Stock Intelligence - Starting Up...
echo  ================================================
echo.

:: ── Check Python ────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b
)

:: ── Check Node ───────────────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Node.js not found. Install from https://nodejs.org
    pause
    exit /b
)

:: ── Set paths ────────────────────────────────────────────────────────────────
set ROOT=%~dp0
set BACKEND=%ROOT%backend
set FRONTEND=%ROOT%frontend

:: ── Install backend deps (first run only) ────────────────────────────────────
echo  [1/4] Checking backend dependencies...
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo        Installing Python packages (first run - please wait)...
    pip install -r "%BACKEND%\requirements.txt" --quiet
    echo        Done.
) else (
    echo        Already installed. Skipping.
)

:: ── Install frontend deps (first run only) ───────────────────────────────────
echo  [2/4] Checking frontend dependencies...
if not exist "%FRONTEND%\node_modules" (
    echo        Installing Node packages (first run - please wait)...
    cd /d "%FRONTEND%"
    npm install --silent
    echo        Done.
) else (
    echo        Already installed. Skipping.
)

:: ── Create .env.local if missing ─────────────────────────────────────────────
if not exist "%FRONTEND%\.env.local" (
    echo VITE_API_BASE=http://localhost:8000 > "%FRONTEND%\.env.local"
)

:: ── Start Backend ─────────────────────────────────────────────────────────────
echo  [3/4] Starting backend on http://localhost:8000 ...
start "DericBI Backend" cmd /k "cd /d "%BACKEND%" && uvicorn app:app --reload --port 8000"

:: ── Wait for backend to be ready ─────────────────────────────────────────────
echo        Waiting for backend to wake up...
timeout /t 4 /nobreak >nul

:waitloop
curl -s http://localhost:8000 >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto waitloop
)
echo        Backend is live!

:: ── Start Frontend ────────────────────────────────────────────────────────────
echo  [4/4] Starting frontend on http://localhost:5173 ...
start "DericBI Frontend" cmd /k "cd /d "%FRONTEND%" && npm run dev"

:: ── Wait for frontend then open browser ───────────────────────────────────────
echo        Waiting for frontend to compile...
timeout /t 5 /nobreak >nul

:waitfront
curl -s http://localhost:5173 >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto waitfront
)

echo.
echo  ================================================
echo    Everything is running!
echo    Opening browser...
echo  ================================================
echo.
start "" "http://localhost:5173"

echo  Backend  : http://localhost:8000
echo  API Docs : http://localhost:8000/docs
echo  Frontend : http://localhost:5173
echo.
echo  Close the two terminal windows to stop the servers.
echo.
pause
