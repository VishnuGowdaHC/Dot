@echo off
setlocal enabledelayedexpansion
title Dot Assistant Setup Launcher

echo ========================================================
echo   Dot Setup & Virtual Environment Bootstrap
echo ========================================================
echo.

:: 1. Check if .venv already exists
if exist ".venv\Scripts\python.exe" (
    echo [OK] Virtual environment found (.venv)
    goto LAUNCH
)

:: 2. Check if Python 3.12 is available on the system
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=py -3.12"
    goto CREATE_VENV
)

:: Fallback check if default 'python' is 3.12
python --version 2>&1 | findstr "3.12" >nul
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto CREATE_VENV
)

:: 3. Python 3.12 is missing - Prompt user to auto-install via winget
echo [!] Python 3.12 is required (for PyTorch, ONNX, and faster-whisper compatibility).
echo [!] Python 3.12 was not detected on your system.
echo.
set /p INSTALL_PY="Would you like to auto-install Python 3.12 using Windows Package Manager (winget)? (Y/N): "

if /i "%INSTALL_PY%"=="Y" (
    echo.
    echo Installing Python 3.12...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Automatic installation failed. Please install Python 3.12 manually from:
        echo https://www.python.org/downloads/release/python-3128/
        pause
        exit /b 1
    )
    echo.
    echo [OK] Python 3.12 installed!
    set "PY_CMD=py -3.12"
) else (
    echo.
    echo Setup aborted. Please install Python 3.12 manually and restart this script.
    pause
    exit /b 1
)

:: 4. Create .venv
:CREATE_VENV
echo.
echo [*] Creating isolated virtual environment (.venv)...
%PY_CMD% -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

:: 5. Install requirements in .venv
echo [*] Installing requirements into .venv (this may take a few minutes)...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation encountered errors.
    pause
    exit /b 1
)

:: 6. Launch Setup GUI using .venv
:LAUNCH
echo.
echo [*] Starting Dot Setup Wizard...
.venv\Scripts\python.exe setup.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Setup script exited with an error. Check error.log for details.
    pause
)
