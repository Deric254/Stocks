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

:: Get the folder this bat file lives in
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

echo  Root folder : %ROOT%
echo  Backend     : %BACKEND%
echo  Frontend    : %FRONTEND%
echo.

:: CHECK PYTHON
echo  [CHECK] Looking for Python...
python --version
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python is NOT installed or not in PATH.
    echo  Please install from: https://python.org/downloads
    echo  IMPORTANT: Tick "Add Python to PATH" during install
    echo.
    pause
    exit /b 1
)
echo  [OK] Python found.
echo.

:: CHECK PIP via python -m pip (works even when pip.exe is not in PATH)
echo  [CHECK] Checking pip via python -m pip...
python -m pip --version
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] pip is not available inside your Python install.
    echo  Fix it by running this once:  python -m ensurepip --upgrade
    echo.
    pause
    exit /b 1
)
echo  [OK] pip found.
echo.

:: CHECK NODE
echo  [CHECK] Looking for Node.js...
node --version
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Node.js is NOT installed or not in PATH.
    echo  Please install from: https://nodejs.org  (choose LTS version)
    echo  Then restart your computer and try again.
    echo.
    pause
    exit /b 1
)
echo  [OK] Node found.
echo.

:: CHECK NPM
echo  [CHECK] Looking for npm...
npm --version
if %errorlevel% neq 0 (
    echo  [ERROR] npm not found. Reinstall Node.js from https://nodejs.org
    pause
    exit /b 1
)
echo  [OK] npm found.
echo.

:: INSTALL PYTHON PACKAGES
echo  [STEP 1/4] Installing Python packages...
echo  (This may take a minute on first run)
echo.
python -m pip install -r "%BACKEND%\requirements.txt"
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Failed to install Python packages.
    echo  Try running manually:
    echo    cd "%BACKEND%"
    echo    python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo.
echo  [OK] Python packages installed.
echo.

:: INSTALL NODE PACKAGES
echo  [STEP 2/4] Installing Node packages...
echo  (This may take a minute on first run)
echo.
cd /d "%FRONTEND%"
npm install
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Failed to install Node packages.
    echo  Try running manually:
    echo    cd "%FRONTEND%"
    echo    npm install
    echo.
    pause
    exit /b 1
)
echo.
echo  [OK] Node packages installed.
echo.

:: CREATE .env.local
if not exist "%FRONTEND%\.env.local" (
    echo  [STEP 3/4] Creating .env.local...
    echo VITE_API_BASE=http://localhost:8000> "%FRONTEND%\.env.local"
    echo  [OK] .env.local created.
) else (
    echo  [STEP 3/4] .env.local already exists. Skipping.
)
echo.

:: START BACKEND
echo  [STEP 4/4] Starting backend server...
cd /d "%BACKEND%"
start "Stock Intel - Backend (keep open)" cmd /k "color 0B && echo. && echo  Stock Intel BACKEND running at http://localhost:8000 && echo  Press Ctrl+C to stop. && echo. && python -m uvicorn app:app --reload --port 8000"
echo  [OK] Backend window opened.
echo.

:: WAIT FOR BACKEND
echo  Waiting for backend to start (up to 30 seconds)...
set /a tries=0
:waitbackend
set /a tries+=1
if %tries% gtr 15 (
    echo  Backend took too long - continuing anyway...
    goto startfrontend
)
timeout /t 2 /nobreak >nul
curl -s --max-time 2 http://localhost:8000 >nul 2>&1
if %errorlevel% neq 0 (
    echo  Still waiting... attempt %tries% of 15
    goto waitbackend
)
echo  [OK] Backend is responding!
echo.

:: START FRONTEND
:startfrontend
echo  Starting frontend server...
cd /d "%FRONTEND%"
start "Stock Intel - Frontend (keep open)" cmd /k "color 0E && echo. && echo  Stock Intel FRONTEND running at http://localhost:5173 && echo  Press Ctrl+C to stop. && echo. && npm run dev"
echo  [OK] Frontend window opened.
echo.

:: WAIT FOR FRONTEND
echo  Waiting for frontend to compile (up to 30 seconds)...
set /a tries=0
:waitfrontend
set /a tries+=1
if %tries% gtr 15 (
    echo  Opening browser anyway...
    goto openbrowser
)
timeout /t 2 /nobreak >nul
curl -s --max-time 2 http://localhost:5173 >nul 2>&1
if %errorlevel% neq 0 (
    echo  Still compiling... attempt %tries% of 15
    goto waitfrontend
)
echo  [OK] Frontend is ready!
echo.

:: OPEN BROWSER
:openbrowser
echo  Opening browser...
start "" "http://localhost:5173"

echo.
echo  =====================================================
echo    Stock Intel is RUNNING!
echo.
echo    Frontend  : http://localhost:5173
echo    Backend   : http://localhost:8000
echo    API Docs  : http://localhost:8000/docs
echo.
echo    To STOP: close the two server windows.
echo  =====================================================
echo.
pause