@echo off
chcp 65001 >nul
title Stock Intel - Starting...
echo.
echo  ============================================
echo   Stock Intel - NSE Investment Intelligence
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from python.org and re-run this file.
    echo         Recommended: Python 3.11 or 3.12 - see note below.
    pause & exit
)

:: Note (not a blocker): very new Python versions sometimes lack
:: prebuilt installer packages for a library or two, which would make
:: pip compile from source instead - slower, but the install below
:: will just try it directly with whatever Python you have. If it
:: fails, the error handling further down explains what happened.
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo       Using Python %PYVER%

:: Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from nodejs.org and re-run this file.
    pause & exit
)

:: Install backend deps if needed
echo [1/4] Checking backend dependencies...
echo       (first run only - this downloads pandas/numpy/fastapi and can take
echo        1-3 minutes with NO visible progress. This is normal, not frozen.
echo        If it's been more than 5 minutes, check your internet connection.)
echo.
cd backend
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Backend dependency install failed. See the message above.
    echo.
    echo         If you saw "cargo" or "rustc" or "maturin" in the error -
    echo         your Python version is too new to have a ready-made install
    echo         for one of the libraries, and there is no C/Rust compiler
    echo         on this machine to build it manually. Easiest fix: install
    echo         Python 3.11 or 3.12 from python.org alongside your current
    echo         Python - nothing gets removed - then run this file again.
    echo.
    echo         Otherwise, try: run this file as Administrator, or check
    echo         your internet connection.
    cd ..
    pause & exit
)
echo.
echo [1/4] Backend dependencies OK.
cd ..

:: Install frontend deps if needed
echo [2/4] Checking frontend dependencies...
cd frontend
if not exist node_modules (
    echo       Installing npm packages - first run only, can take 1-2 minutes...
    call npm install
    if errorlevel 1 (
        echo.
        echo [ERROR] Frontend dependency install failed. See the message above.
        cd ..
        pause & exit
    )
) else (
    echo       Already installed.
)
cd ..
echo [2/4] Frontend dependencies OK.

:: Optional: warn if FRED_API_KEY isn't set (system still runs fine without it)
if "%FRED_API_KEY%"=="" (
    echo [3/4] Note: FRED_API_KEY not set - global macro indicators such as
    echo        rates, inflation, GDP, and PMI will show as not configured.
    echo        Everything else works normally.
    echo        Get a free key at fred.stlouisfed.org/docs/api/api_key.html if you want it.
) else (
    echo [3/4] FRED_API_KEY detected - global macro indicators enabled.
)

:: Start backend
echo [4/4] Starting backend on http://localhost:8000 ...
start "Stock Intel Backend" cmd /k "cd backend && python app.py"
timeout /t 4 /nobreak >nul

:: Start frontend
echo Starting frontend on http://localhost:5173 ...
start "Stock Intel Frontend" cmd /k "cd frontend && npm run dev"
timeout /t 4 /nobreak >nul

:: Open browser
echo Opening browser...
start http://localhost:5173

echo.
echo  ============================================
echo   Stock Intel is running
echo  ============================================
echo   App:            http://localhost:5173
echo   API:            http://localhost:8000
echo   System status:  http://localhost:8000/api/system-status
echo                    (check this first if anything looks wrong)
echo.
echo   Close the two black terminal windows to stop the app.
echo  ============================================
echo.
pause
