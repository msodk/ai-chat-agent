@echo off
REM AI Chat Desktop - TTS bridge stopper (ASCII only on purpose)
REM
REM Why ASCII only: cmd.exe parses .bat byte-by-byte. When a .bat contains
REM multi-byte CJK text (even in REM/echo), cmd's internal read offset drifts
REM and lines get truncated (e.g. "echo Stopping..." becomes "Stopping..." and
REM is run as a command -> "'Stopping' is not recognized"). UTF-8 BOM / chcp
REM cannot fully fix it. Keep this file 100% ASCII; any Chinese text should be
REM emitted from Python, not from the batch file.
REM
REM Do NOT add Chinese characters to this file.

cd /d "%~dp0"

echo Stopping TTS bridge (port 9880)...

rem Main: kill by window title set at launch (cascades to python via /T)
taskkill /F /FI "WINDOWTITLE eq TTS_Bridge_Service" /T >nul 2>&1

rem Fallback: kill by port 9880 (netstat parse + taskkill /T; never by process name)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9880 " ^| findstr "LISTENING"') do (
    echo [KILL] Stopping PID=%%a on port 9880...
    taskkill /F /T /pid %%a >nul 2>&1
)

echo.
echo [OK] TTS bridge service stopped.
echo.
ping -n 3 127.0.0.1 >nul 2>&1
