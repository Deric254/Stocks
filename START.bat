@echo off
title Stock Intel — Starting...
echo.
echo  ====================================
echo   Stock Intel — NSE + Gold Platform  
echo  ====================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from python.org
    pause & exit
)

:: Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from nodejs.org
    pause & exit
)

:: Install backend deps if needed
echo [1/3] Checking backend dependencies...
cd backend
pip install -r requirements.txt -q
cd ..

:: Install frontend deps if needed
echo [2/3] Checking frontend dependencies...
cd frontend
if not exist node_modules (
    echo Installing npm packages (first time only)...
    npm install
)
cd ..

:: Start backend
echo [3/3] Starting backend...
start "Stock Intel Backend" cmd /k "cd backend && python app.py"
timeout /t 3 /nobreak >nul

:: Start frontend
echo Starting frontend...
start "Stock Intel Frontend" cmd /k "cd frontend && npm run dev"
timeout /t 4 /nobreak >nul

:: Open browser
echo Opening browser...
start http://localhost:5173

echo.
echo  ✓ Stock Intel is running!
echo  ✓ Open: http://localhost:5173
echo  ✓ Close the two terminal windows to stop.
echo.
pause
