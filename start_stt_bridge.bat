@echo off
REM AI Chat Desktop - STT bridge launcher (ASCII only on purpose)
REM
REM Why ASCII only: same reason as close_tts_bridge.bat - cmd.exe byte-drift on
REM CJK text. Keep this file 100% ASCII. See close_tts_bridge.bat for details.
REM
REM Do NOT add Chinese characters to this file.

cd /d "%~dp0"
title TTS Bridge STT Launcher
set "PY=%~dp0.venv\Scripts\python.exe"
set "SCRIPT=%~dp0bridge_stt_server.py"

echo Checking port 4316 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":4316 " ^| findstr "LISTENING"') do (
    echo Port 4316 is already in use. The STT service may already be running.
    echo If you want to restart it, run close_stt_bridge.bat first.
    echo Press any key to exit.
    pause
    exit /b
)

echo Starting local STT bridge (whisper small, cpu, offline) ...
start "TTS_Bridge_STT" "%PY%" "%SCRIPT%"
echo [OK] STT service launched in a separate window.
echo Keep that window open. To stop it, run close_stt_bridge.bat.
echo Press any key to close this launcher (service keeps running).
pause
