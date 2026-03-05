@echo off
title Stock Intel Launcher
color 0A
cls

echo.
echo  =====================================================
echo    Stock Intel - Cut through the noise.
echo    Starting up - please wait...
echo  =====================================================
echo.

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

echo  Root     : %ROOT%
echo  Backend  : %BACKEND%
echo  Frontend : %FRONTEND%
echo.

echo  [CHECK] Python...
python --version
if %errorlevel% neq 0 ( echo  [ERROR] Python not found. Install from https://python.org & pause & exit /b 1 )
echo  [OK] Python found.
echo.

echo  [CHECK] pip...
python -m pip --version
if %errorlevel% neq 0 ( echo  [ERROR] pip missing. Run: python -m ensurepip --upgrade & pause & exit /b 1 )
echo  [OK] pip found.
echo.

echo  [CHECK] Node.js...
node --version
if %errorlevel% neq 0 ( echo  [ERROR] Node.js not found. Install from https://nodejs.org & pause & exit /b 1 )
echo  [OK] Node found.
echo.

echo  [CHECK] npm...
npm --version
if %errorlevel% neq 0 ( echo  [ERROR] npm not found. Reinstall Node.js & pause & exit /b 1 )
echo  [OK] npm found.
echo.

echo  [STEP 1/4] Installing Python packages...
python -m pip install -r "%BACKEND%\requirements.txt"
if %errorlevel% neq 0 ( echo  [ERROR] Python install failed & pause & exit /b 1 )
echo  [OK] Python packages ready.
echo.

echo  [STEP 2/4] Installing Node packages...
cd /d "%FRONTEND%"
npm install
if %errorlevel% neq 0 ( echo  [ERROR] npm install failed & pause & exit /b 1 )
echo  [OK] Node packages ready.
echo.

echo  [STEP 3/4] Setting up environment...
if not exist "%FRONTEND%\.env.local" (
    echo VITE_API_BASE=http://localhost:8000> "%FRONTEND%\.env.local"
    echo  [OK] .env.local created.
) else (
    echo  [OK] .env.local exists.
)
echo.

echo  [STEP 4/4] Launching servers...
cd /d "%BACKEND%"
start "Stock Intel - BACKEND" cmd /k "color 0B && echo. && echo  BACKEND: http://localhost:8000 && echo. && python -m uvicorn app:app --reload --port 8000"

timeout /t 5 /nobreak >nul

cd /d "%FRONTEND%"
start "Stock Intel - FRONTEND" cmd /k "color 0E && echo. && echo  FRONTEND: http://localhost:5173 && echo. && npm run dev"

echo  Waiting for frontend to compile...
timeout /t 10 /nobreak >nul

echo  Opening browser...
start "" "http://localhost:5173"

echo.
echo  =====================================================
echo    Stock Intel is RUNNING!
echo    App      : http://localhost:5173
echo    API      : http://localhost:8000
echo    API Docs : http://localhost:8000/docs
echo    Close the two server windows to stop.
echo  =====================================================
echo.
pause
