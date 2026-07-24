@echo off
title Proomnes Bot Launcher (Safe Mode)

REM ============================================
REM 1) CHECK PYTHON
REM ============================================
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed!
    pause
    exit /b 1
)
echo Python OK ✓
echo.

REM ============================================
REM 2) CHECK OR CREATE VENV
REM ============================================
echo Checking venv...
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv venv
)

if not exist "venv\Scripts\python.exe" (
    echo ERROR: venv creation FAILED!
    pause
    exit /b 1
)

echo venv ready ✓
echo.

REM ============================================
REM 3) ACTIVATE VENV
REM ============================================
echo Activating venv...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate venv!
    pause
    exit /b 1
)
echo venv activated ✓
echo.

REM ============================================
REM 4) UPDATE PIP INSIDE VENV ONLY
REM ============================================
echo Updating pip inside venv...
python -m pip install --upgrade pip
echo pip updated ✓
echo.

REM ============================================
REM 5) AUTO-INSTALL REQUIRED PACKAGES
REM ============================================
echo Checking required packages...

set PACKAGES=aiogram python-dotenv pillow psutil requests openpyxl babel aiohttp aiofiles

for %%p in (%PACKAGES%) do (
    pip show %%p >nul 2>&1
    if errorlevel 1 (
        echo Installing missing package: %%p
        pip install %%p
    ) else (
        echo Package exists: %%p ✓
    )
)

echo All packages OK ✓
echo.

REM ============================================
REM 6) CREATE ESSENTIAL FILES IF MISSING
REM ============================================
if not exist ".env" (
    echo Creating .env...
    echo BOT_TOKEN= >> .env
)

if not exist "button_labels.json" (
    echo Creating button_labels.json...
    echo {} > button_labels.json
)

echo All essential files exist ✓
echo.

REM ============================================
REM 7) SELECT BOT FILE
REM ============================================
echo Choose bot file:
echo 1 - main.py
echo 2 - comprehensive_bot.py
echo 3 - advanced_bot.py
echo 4 - fixed_bot.py
echo 5 - simple_bot.py
echo.

set /p choice="Enter number: "

if "%choice%"=="1" set script=main.py
if "%choice%"=="2" set script=comprehensive_bot.py
if "%choice%"=="3" set script=advanced_bot.py
if "%choice%"=="4" set script=fixed_bot.py
if "%choice%"=="5" set script=simple_bot.py

if "%script%"=="" (
    echo ERROR: Invalid selection!
    pause
    exit /b 1
)

echo Running %script% ...
python "%script%"

echo.
echo Bot stopped.
pause
