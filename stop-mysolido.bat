@echo off
setlocal enabledelayedexpansion
title MySolido Stoppen
echo.
echo   MySolido wordt gestopt...
echo.

REM Stop Flask (Python op poort 5000)
set "found_flask=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>nul
    set "found_flask=1"
)
if "!found_flask!"=="1" (
    echo   [OK] Flask gestopt
) else (
    echo   [--] Flask was niet actief
)

REM Stop CSS (Node op poort 3000)
set "found_css=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>nul
    set "found_css=1"
)
if "!found_css!"=="1" (
    echo   [OK] Solid Server gestopt
) else (
    echo   [--] Solid Server was niet actief
)

echo.
echo   MySolido is gestopt.
echo.
timeout /t 3 /nobreak >nul
