@echo off
echo ========================================================
echo Booting Local Inference Engine (CUDA)...
echo ========================================================
cd bin
start "" cmd /c "llama-server.exe -m gemma-4-E4B_q4_0-it.gguf --mmproj gemma-4-E4B-it-mmproj.gguf --port 11434 -c 8192 -fa on -ctk q8_0 -ctv q8_0 -ngl 99 --temp 0.0 --alias dot-engine"
cd ..

timeout /t 5

echo ========================================================
echo Booting Python Orchestrator...
echo ========================================================
start "" cmd /c "cd dum-e && py -m uvicorn server:app --port 3000"

echo ========================================================
echo Launching Dot UI...
echo ========================================================
start "" cmd /c "cd dum-e && neu run"
