@echo off
title PayPal Conditional Autopay - Version 2
cd /d "%~dp0"

echo =========================================================
echo    PayPal Conditional Autopay - AI Mandate Firewall
echo =========================================================
echo.

:: 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo Please install Python 3.10+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b
)

echo [1/3] Python detected:
python --version
echo.

:: 2. Install required dependencies
echo [2/3] Checking dependencies (Flask, Requests)...
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Pip install had an issue, trying to start app anyway...
) else (
    echo [OK] All dependencies ready.
)
echo.

:: 3. Launch Flask Server
echo [3/3] Starting web application server...
echo.
echo =========================================================
echo  Server is LIVE at: http://localhost:5000
echo  Press Ctrl+C in this terminal window to stop the server.
echo =========================================================
echo.

:: Auto-open browser after 2 seconds
start "" http://localhost:5000

python app.py
pause
