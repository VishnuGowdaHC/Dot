@echo off
setlocal
title Dot Assistant Setup Bootstrap

:: Pin working directory to script location
cd /d "%~dp0"
set "LOG_FILE=%~dp0error.log"
set "VENV_DIR=%~dp0.venv"

echo ========================================================
echo   Dot Setup and Environment Bootstrap
echo ========================================================
echo.

:: ============================================================
:: STEP 1: .venv existence check - skip Python discovery if ready
:: ============================================================
if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [OK] Virtual environment found at %VENV_DIR%
    goto ACTIVATE_VENV
)

:: ============================================================
:: STEP 2: Find a Python interpreter to create the venv
:: ============================================================
echo [*] No virtual environment found. Setting one up...
set "PY_CMD="

py -3.12 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto CREATE_VENV
)

python --version 2>&1 | findstr "3.12" >nul
if not errorlevel 1 (
    set "PY_CMD=python"
    goto CREATE_VENV
)

py --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py"
    goto CREATE_VENV
)

python --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto CREATE_VENV
)

:: No Python at all -> offer winget or manual install
echo [-] Python is required but was not detected on your system.
echo.

winget --version >nul 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] [ERROR] No Python found and winget unavailable. >> "%LOG_FILE%"
    echo [-] winget is not available on this device.
    echo Please install Python 3.12 manually from:
    echo https://www.python.org/downloads/release/python-3128/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

set "INSTALL_PY=N"
set /p INSTALL_PY="Auto-install Python 3.12 via winget? (Y/N): "
if /i "%INSTALL_PY%"=="Y" goto DO_WINGET

echo [%DATE% %TIME%] [INFO] User declined Python auto-install. >> "%LOG_FILE%"
echo Setup cancelled. Install Python 3.12 and re-run start_setup.bat.
pause
exit /b 1

:DO_WINGET
echo.
echo [*] Installing Python 3.12 via winget...
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [%DATE% %TIME%] [ERROR] winget Python install failed. >> "%LOG_FILE%"
    echo [ERROR] Auto-install failed. Get Python 3.12 from:
    echo https://www.python.org/downloads/release/python-3128/
    pause
    exit /b 1
)
echo [OK] Python 3.12 installed.
set "PY_CMD=py -3.12"

:: ============================================================
:: STEP 3: Create the .venv folder and venv inside it
:: ============================================================
:CREATE_VENV
if "%PY_CMD%"=="" set "PY_CMD=py -3.12"

echo.
echo [*] Creating .venv directory...
if not exist "%VENV_DIR%" mkdir "%VENV_DIR%"

echo [*] Building virtual environment using %PY_CMD%...
%PY_CMD% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [%DATE% %TIME%] [ERROR] venv creation failed: %PY_CMD% -m venv "%VENV_DIR%" >> "%LOG_FILE%"
    echo [ERROR] Could not create virtual environment.
    pause
    exit /b 1
)
echo [OK] Virtual environment created.

:: ============================================================
:: STEP 4: Activate the venv
:: ============================================================
:ACTIVATE_VENV
echo.
echo [*] Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo [%DATE% %TIME%] [ERROR] Failed to activate venv at "%VENV_DIR%\Scripts\activate.bat" >> "%LOG_FILE%"
    echo [ERROR] Could not activate .venv. Try deleting .venv and re-running.
    pause
    exit /b 1
)
echo [OK] Virtual environment activated.

:: Verify python is now the venv python
python --version
echo     Running from: %VENV_DIR%\Scripts\python.exe

:: ============================================================
:: STEP 5: Install all dependencies inside the activated venv
:: ============================================================
echo.
echo [*] Upgrading pip, setuptools, and wheel...
python -m pip install --upgrade pip setuptools wheel --quiet

echo [*] Installing project dependencies from requirements.txt...
echo     This may take several minutes for PyTorch, audio, and ML packages.
python -m pip install -r "%~dp0requirements.txt" > "%~dp0pip_install.log" 2>&1
if not errorlevel 1 goto PIP_OK

echo [%DATE% %TIME%] [ERROR] pip install -r requirements.txt failed. See pip_install.log >> "%LOG_FILE%"
type "%~dp0pip_install.log" >> "%LOG_FILE%" 2>nul
echo.
echo [ERROR] Dependency installation failed.
echo --------------------------------------------------------
powershell -Command "if (Test-Path '%~dp0pip_install.log') { Get-Content '%~dp0pip_install.log' -Tail 20 } else { Write-Host 'pip_install.log not found' }"
echo --------------------------------------------------------
echo Details saved to error.log and pip_install.log.
pause
exit /b 1

:PIP_OK
echo [OK] All dependencies installed.

:: ============================================================
:: STEP 6: Playwright browser binaries
:: ============================================================
echo.
echo [*] Installing Playwright Chromium browser...
python -m playwright install chromium >nul 2>&1
if errorlevel 1 echo [%DATE% %TIME%] [WARNING] Playwright chromium install had an issue. >> "%LOG_FILE%"
if errorlevel 1 echo [Warning] Playwright chromium install had an issue, but setup can continue.

:: ============================================================
:: STEP 7: Launch Setup Wizard - still inside activated venv
:: ============================================================
echo.
echo [*] Launching Dot Setup Wizard...
python "%~dp0setup.py"
if errorlevel 1 (
    echo [%DATE% %TIME%] [ERROR] setup.py crashed. >> "%LOG_FILE%"
    echo.
    echo [ERROR] Setup GUI exited with an error. Check error.log.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   Setup complete.
echo ========================================================
pause
