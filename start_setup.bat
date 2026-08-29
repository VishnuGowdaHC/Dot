@echo off
setlocal enabledelayedexpansion
title Dot Assistant Setup Bootstrap

:: Ensure script runs from its own directory
cd /d "%~dp0"
set "LOG_FILE=%~dp0error.log"

echo ========================================================
echo   Dot Setup and Environment Bootstrap
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

:: Python 3.12 not found -> check winget
echo [!] Python 3.12 is required for local inference, PyTorch CUDA, and audio models.
echo [!] Python 3.12 was not detected on your system.
echo.

winget --version >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] [ERROR] Python 3.12 is not installed and winget is not available on this system. >> "%LOG_FILE%"
    echo [!] Windows Package Manager (winget) was not found on this device.
    echo Please download and install Python 3.12 manually from:
    echo https://www.python.org/downloads/release/python-3128/
    echo.
    echo (Be sure to check "Add Python 3.12 to PATH" during installation)
    echo.
    pause
    exit /b 1
)

set "INSTALL_PY=N"
set /p INSTALL_PY="Would you like to auto-install Python 3.12 using Windows Package Manager (winget)? (Y/N): "
if /i "!INSTALL_PY!"=="Y" (
    echo.
    echo [*] Installing Python 3.12 via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [%date% %time%] [ERROR] Automatic installation of Python 3.12 via winget failed with exit code !errorlevel!. >> "%LOG_FILE%"
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
    echo [%date% %time%] [INFO] Setup aborted by user: declined auto-install of Python 3.12. >> "%LOG_FILE%"
    echo.
    echo Setup cancelled. Please install Python 3.12 and restart start_setup.bat.
    pause
    exit /b 1
)

:FOUND_PYTHON
if "!PY_CMD!"=="" set "PY_CMD=py -3.12"

:: 2. Create isolated .venv if not present
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [*] Creating isolated virtual environment (.venv)...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [%date% %time%] [ERROR] Failed to create virtual environment using command '%PY_CMD% -m venv .venv'. >> "%LOG_FILE%"
        echo [ERROR] Failed to create virtual environment with %PY_CMD%.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created (.venv)
) else (
    echo [OK] Existing virtual environment found (.venv)
)

:: 3. Install all requirements.txt dependencies into .venv
echo.
echo [*] Upgrading pip in .venv...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet

echo [*] Installing all dependencies in .venv from requirements.txt...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [%date% %time%] [ERROR] pip install -r requirements.txt failed in .venv. >> "%LOG_FILE%"
    echo.
    echo [ERROR] Failed to install requirements into .venv.
    echo Please review the error output above and check error.log.
    pause
    exit /b 1
)

:: 4. Ensure Playwright browser binaries
echo.
echo [*] Ensuring Playwright browser binaries in .venv...
.venv\Scripts\python.exe -m playwright install chromium
if errorlevel 1 (
    echo [%date% %time%] [WARNING] Playwright chromium browser binary installation returned non-zero code. >> "%LOG_FILE%"
    echo [Warning] Playwright chromium install encountered an issue (non-fatal).
)

:: 5. Launch Setup GUI using .venv
echo.
echo [*] Launching Dot Setup Wizard...
.venv\Scripts\python.exe setup.py
if errorlevel 1 (
    echo [%date% %time%] [ERROR] setup.py terminated unexpectedly with exit code !errorlevel!. >> "%LOG_FILE%"
    echo.
    echo [ERROR] Setup GUI exited with an error. Check error.log for details.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   Setup Wizard process finished.
echo ========================================================
pause
