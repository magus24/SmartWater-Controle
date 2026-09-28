@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title SmartWater Control

set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%"

echo ============================================
echo    SMART WATER CONTROL  -  quick start
echo ============================================
echo.

rem ---------- 1) check whether the server is already running ----------
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if not errorlevel 1 (
    echo [OK] Port %PORT% is busy - the server is already running.
    echo      Opening the browser...
    start "" "%URL%"
    exit /b 0
)

rem ---------- 2) find Python ----------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo [ERROR] Python was not found in PATH.
    echo         Install Python 3.10+ and run this file again.
    pause
    exit /b 1
)
echo [OK] Python: %PY%

rem ---------- 3) check / install dependencies ----------
%PY% -c "import fastapi, uvicorn, pydantic" >nul 2>nul
if errorlevel 1 (
    echo [..] Installing dependencies from requirements.txt, please wait...
    %PY% -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed.
) else (
    echo [OK] Dependencies are installed.
)

rem ---------- 4) open the browser as soon as the server answers ----------
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "$u='%URL%'; for($i=0;$i -lt 120;$i++){ try{ if((Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200){ Start-Process $u; break } }catch{}; Start-Sleep -Milliseconds 500 }"

rem ---------- 5) run the server ----------
echo [..] Starting the server on %URL%
echo     Docs (Swagger): %URL%/docs
echo     Press CTRL+C to stop.
echo.
%PY% -m uvicorn main:app --host 127.0.0.1 --port %PORT% --reload
set "RC=%errorlevel%"

echo.
if not "%RC%"=="0" (
    echo [ERROR] The server stopped with code %RC%. See the log above.
) else (
    echo [OK] The server has been stopped.
)
pause
