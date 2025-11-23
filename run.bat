@echo off
title Document Q&A System - Offline Mode

echo ====================================
echo    DOCUMENT Q&A SYSTEM - OFFLINE MODE
echo ====================================

echo.
echo Checking system setup...

REM Check if setup was completed
if not exist "venv" (
    echo ERROR: Virtual environment not found!
    echo Please run 'setup.bat' first with internet connection.
    pause
    exit /b 1
)

if not exist "models\all-MiniLM-L6-v2" (
    echo ERROR: AI models not found!
    echo Please run 'setup.bat' first with internet connection.
    pause
    exit /b 1
)

echo ✓ Virtual environment: Found
echo ✓ AI models: Found

echo.
echo Activating virtual environment...
call venv\Scripts\activate

echo.
echo Setting up offline environment...
set TRANSFORMERS_OFFLINE=1
set HF_DATASETS_OFFLINE=1
set HF_HUB_OFFLINE=1
set TF_CPP_MIN_LOG_LEVEL=2

echo ✓ Environment configured for offline operation
echo.
echo Starting Document Q&A System...
echo.
echo 📍 Access the application at: http://localhost:5001
echo 🔧 Health check: http://localhost:5001/health
echo 🛡️  Mode: Fully Offline
echo.

REM Run the application
python app.py

echo.
echo Application closed.
pause