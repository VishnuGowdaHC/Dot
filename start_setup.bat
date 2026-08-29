@echo off
setlocal
title Dot Assistant Setup Launcher

echo ========================================================
echo   Dot Setup Wizard Bootstrap
echo ========================================================
echo.

:: 1. Locate Python 3.12 interpreter
set "PY_CMD="

py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto FOUND_PYTHON
)

python --version 2>&1 | findstr "3.12" >nul
if not errorlevel 1 (
    set "PY_CMD=python"
    goto FOUND_PYTHON
)

:: Python 3.12 not found -> Check if winget is installed
echo [!] Python 3.12 is required for local inference, PyTorch CUDA, and audio models.
echo [!] Python 3.12 was not detected on your system.
echo.

winget --version >nul 2>&1
if errorlevel 1 (
    echo [!] Windows Package Manager (winget) was not found on this device.
    echo Please download and install Python 3.12 manually from:
    echo https://www.python.org/downloads/release/python-3128/
    echo.
    echo (Be sure to check "Add Python 3.12 to PATH" during installation)
    echo.
    pause
    exit /b 1
)

:: winget is available on this device -> Prompt user
set /p INSTALL_PY="Would you like to auto-install Python 3.12 using Windows Package Manager (winget)? (Y/N): "

if /i "%INSTALL_PY%"=="Y" (
    echo.
    echo [*] Installing Python 3.12 via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
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
    echo Setup cancelled. Please install Python 3.12 and restart start_setup.bat.
    pause
    exit /b 1
)

:FOUND_PYTHON
echo [*] Checking setup dependencies (customtkinter, psutil, requests, pyyaml)...
%PY_CMD% -c "import customtkinter, psutil, requests, yaml" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing missing setup modules...
    %PY_CMD% -m pip install psutil customtkinter requests pyyaml
    if errorlevel 1 (
        echo [ERROR] Failed to install setup dependencies.
        pause
        exit /b 1
    )
)

echo [*] Launching Dot Setup GUI...
%PY_CMD% setup.py
if errorlevel 1 (
    echo.
    echo [ERROR] Setup GUI exited with an error. Check error.log for details.
    pause
)
