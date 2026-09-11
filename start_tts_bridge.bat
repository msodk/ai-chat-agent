@echo off
REM AI Chat Desktop - TTS bridge launcher (ASCII only on purpose)
REM
REM Why ASCII only: same reason as close_tts_bridge.bat - cmd.exe byte-drift on
REM CJK text. Keep this file 100% ASCII. See close_tts_bridge.bat for details.
REM
REM Do NOT add Chinese characters to this file.

cd /d "%~dp0"

rem ============================================================
rem  Pre-check port 9880 to prevent port-conflict crash on relaunch
rem ============================================================
set "PORT_BUSY=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9880 " ^| findstr "LISTENING"') do set "PORT_BUSY=1"
if "%PORT_BUSY%"=="1" (
    echo ============================================================
    echo   Port 127.0.0.1:9880 is already in use.
    echo   The TTS bridge service may already be running.
    echo   To restart it, run the STOP batch first:
    echo     %~dp0close_tts_bridge.bat
    echo     or close the existing service window.
    echo ============================================================
    echo.
    pause
    exit /b 0
)

rem ============================================================
rem  Launch python service in a separate window
rem ============================================================
echo ============================================================
echo   Launching TTS Bridge Service...
echo   A new window titled "TTS_Bridge_Service" will appear.
echo   All output is also written to:
echo     %~dp0tts_bridge.log
echo ============================================================
echo.

start "TTS_Bridge_Service" cmd /k "cd /d %~dp0 && title TTS_Bridge_Service && .\.venv\Scripts\python.exe bridge_tts_server.py >> tts_bridge.log 2>&1"

echo [OK] Service launched in its own window.
echo.
echo       Keep the "TTS_Bridge_Service" window OPEN.
echo       If the maid is silent, check tts_bridge.log for errors.
echo       To stop the service, run:  close_tts_bridge.bat
echo.
pause
