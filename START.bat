@echo off
title Stock Intel - Debug Launcher
color 0A
cls

echo =====================================================
echo  Stock Intel - DEBUG MODE
echo  This window will STAY OPEN so you can see errors
echo =====================================================
echo.

:: Set paths
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

echo ROOT     = %ROOT%
echo BACKEND  = %BACKEND%
echo FRONTEND = %FRONTEND%
echo.
echo -----------------------------------------------------
echo STEP 1 - Checking Python
echo -----------------------------------------------------
python --version
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python not found
    echo Install from https://python.org
    echo.
    goto :end
)

echo.
echo -----------------------------------------------------
echo STEP 2 - Checking pip
echo -----------------------------------------------------
python -m pip --version
if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip not found inside Python
    echo Run this to fix: python -m ensurepip --upgrade
    echo.
    goto :end
)

echo.
echo -----------------------------------------------------
echo STEP 3 - Checking Node
echo -----------------------------------------------------
node --version
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Node.js not found
    echo Install from https://nodejs.org then close and reopen this window
    echo.
    goto :end
)

echo.
echo -----------------------------------------------------
echo STEP 4 - Checking npm
echo -----------------------------------------------------
npm --version
if %errorlevel% neq 0 (
    echo.
    echo ERROR: npm not found
    echo Reinstall Node.js from https://nodejs.org
    echo.
    goto :end
)

echo.
echo -----------------------------------------------------
echo STEP 5 - Installing Python packages
echo -----------------------------------------------------
python -m pip install -r "%BACKEND%\requirements.txt"
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python packages failed to install
    echo See error above
    echo.
    goto :end
)

echo.
echo -----------------------------------------------------
echo STEP 6 - Installing Node packages
echo -----------------------------------------------------
cd /d "%FRONTEND%"
npm install
if %errorlevel% neq 0 (
    echo.
    echo ERROR: npm install failed
    echo See error above
    echo.
    goto :end
)

echo.
echo -----------------------------------------------------
echo STEP 7 - Creating .env.local
echo -----------------------------------------------------
if not exist "%FRONTEND%\.env.local" (
    echo VITE_API_BASE=http://localhost:8000> "%FRONTEND%\.env.local"
    echo Created .env.local
) else (
    echo .env.local already exists - skipping
)

echo.
echo -----------------------------------------------------
echo STEP 8 - Starting Backend
echo -----------------------------------------------------
cd /d "%BACKEND%"
start "Stock Intel - BACKEND" cmd /k "python -m uvicorn app:app --reload --port 8000"
echo Backend window launched

echo.
echo Waiting 5 seconds for backend to start...
timeout /t 5 /nobreak

echo.
echo -----------------------------------------------------
echo STEP 9 - Starting Frontend
echo -----------------------------------------------------
cd /d "%FRONTEND%"
start "Stock Intel - FRONTEND" cmd /k "npm run dev"
echo Frontend window launched

echo.
echo Waiting 8 seconds for frontend to compile...
timeout /t 8 /nobreak

echo.
echo -----------------------------------------------------
echo STEP 10 - Opening Browser
echo -----------------------------------------------------
start "" "http://localhost:5173"
echo Browser opened at http://localhost:5173

echo.
echo =====================================================
echo  ALL DONE - Stock Intel should be open in browser
echo  Backend  : http://localhost:8000
echo  Frontend : http://localhost:5173
echo  API Docs : http://localhost:8000/docs
echo =====================================================
echo.

:end
echo.
echo === WINDOW WILL STAY OPEN - read any errors above ===
pause