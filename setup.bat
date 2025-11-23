@echo off
title Document Q&A System - First Time Setup (Internet Required)

echo ================================================
echo    DOCUMENT Q&A SYSTEM - INITIAL SETUP
echo    Internet connection required for this setup
echo ================================================

echo.
echo Step 1: Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

echo ✓ Python found

echo.
echo Step 2: Removing existing virtual environment...
if exist venv (
    echo Removing existing virtual environment...
    rmdir /s /q venv
)

echo.
echo Step 3: Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    echo Please ensure Python venv module is available
    pause
    exit /b 1
)

echo ✓ Virtual environment created

echo.
echo Step 4: Activating virtual environment...
call venv\Scripts\activate

echo.
echo Step 5: Installing dependencies...
if exist requirements.txt (
    pip install --upgrade pip
    echo Installing packages from requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
) else (
    echo ERROR: requirements.txt not found!
    pause
    exit /b 1
)

echo ✓ Dependencies installed

echo.
echo Step 6: Creating models directory...
if not exist "models" mkdir models

echo.
echo Step 7: Downloading AI models for offline use...
echo This may take a few minutes depending on your internet speed...
echo Downloading sentence-transformers/all-MiniLM-L6-v2...

python download_model.py

if errorlevel 1 (
    echo.
    echo ERROR: Model download failed!
    echo Please check your internet connection and run setup.bat again.
    pause
    exit /b 1
)

echo.
echo ================================================
echo    SETUP COMPLETED SUCCESSFULLY!
echo ================================================
echo.
echo ✅ Virtual environment: venv
echo ✅ AI Models: models/all-MiniLM-L6-v2
echo ✅ Dependencies: All packages installed
echo.
echo NEXT STEPS:
echo 1. Ensure Ollama is installed and running
echo 2. Pull the LLM model: ollama pull llama3
echo 3. Run the system offline using: run.bat
echo.
echo The system is now ready for OFFLINE operation!
echo You can disconnect from the internet.
echo.
pause