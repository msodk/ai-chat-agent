@echo off
REM AI Chat Desktop - STT bridge stopper (ASCII only on purpose)
REM
REM Why ASCII only: cmd.exe parses .bat byte-by-byte. CJK text (even in
REM REM/echo) makes cmd's read offset drift and lines get truncated, so
REM "echo Closing..." becomes "Closing..." and is run as a command.
REM Keep this file 100% ASCII. See close_tts_bridge.bat for details.
REM
REM Do NOT add Chinese characters to this file.

cd /d "%~dp0"
title Close TTS Bridge STT
echo Closing local STT bridge on port 4316 ...

rem Main: kill by window title set at launch (cascades to python via /T)
taskkill /F /FI "WINDOWTITLE eq TTS_Bridge_STT" /T >nul 2>&1

rem Fallback: kill by port 4316 (netstat parse + taskkill /T)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":4316 " ^| findstr "LISTENING"') do (
    echo [KILL] Stopping PID=%%a on port 4316...
    taskkill /F /T /pid %%a >nul 2>&1
)

echo Done.
ping -n 3 127.0.0.1 >nul 2>&1
