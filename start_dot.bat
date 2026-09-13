@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Activate the virtual environment
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Could not activate .venv. Run start_setup.bat first.
    pause
    exit /b 1
)

echo ========================================================
echo   Dot is starting up...
echo ========================================================
echo.
echo [1/3] Starting Local Inference Engine (CUDA)...
if not exist "bin\llama-server.exe" (
    echo [ERROR] bin\llama-server.exe was not found! Please run setup.py first.
    pause
    exit /b 1
)
cd bin
start "Dot Inference Engine" cmd /k "llama-server.exe -m gemma-4-E4B_q4_0-it.gguf --mmproj gemma-4-E4B-it-mmproj.gguf --port 11434 -c 8192 -fa on -ngl 99 --temp 0.0 --alias dot-engine"
cd ..

<nul set /p =[1/3] Waiting for engine on port 11434 
set ENGINE_RETRIES=0
:WAIT_ENGINE
powershell -Command "try { $null = (New-Object Net.Sockets.TcpClient('127.0.0.1', 11434)).Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    set /a ENGINE_RETRIES+=1
    if !ENGINE_RETRIES! geq 30 (
        echo  [FAILED]
        echo.
        echo [ERROR] Inference engine failed to start on port 11434 within 60 seconds.
        echo Please inspect the "Dot Inference Engine" window for error details.
        pause
        exit /b 1
    )
    <nul set /p =.
    timeout /t 2 /nobreak >nul
    goto WAIT_ENGINE
)
echo  [DONE]
echo.
echo [2/3] Starting Python Orchestrator...
start "Dot Backend" cmd /k "call .venv\Scripts\activate.bat && cd dum-e && python -m uvicorn server:app --port 3000"

<nul set /p =[2/3] Waiting for orchestrator on port 3000 
set ORCH_RETRIES=0
:WAIT_ORCH
powershell -Command "try { $null = (New-Object Net.Sockets.TcpClient('127.0.0.1', 3000)).Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    set /a ORCH_RETRIES+=1
    if !ORCH_RETRIES! geq 30 (
        echo  [FAILED]
        echo.
        echo [ERROR] Orchestrator failed to start on port 3000 within 60 seconds.
        echo Check the Dot Backend window for error messages.
        pause
        exit /b 1
    )
    <nul set /p =.
    timeout /t 2 /nobreak >nul
    goto WAIT_ORCH
)
echo  [DONE]
echo.
echo [3/3] Launching Dot UI...
start "Dot Frontend" cmd /c "cd dum-e && npx @neutralinojs/neu run"
echo.
echo ========================================================
echo   All systems go. Dot is ready.
echo ========================================================
echo   (You can close this window)
