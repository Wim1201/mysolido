@echo off
title MySolido — Jouw persoonlijke datakluis
color 0A

echo.
echo   ╔═══════════════════════════════════════════╗
echo   ║          MySolido wordt gestart...        ║
echo   ║   Jouw data. Op jouw pc. Jouw voorwaarden ║
echo   ╚═══════════════════════════════════════════╝
echo.

:: Check of Node.js beschikbaar is
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo   [FOUT] Node.js is niet gevonden.
    echo   Download het via https://nodejs.org
    echo.
    pause
    exit /b 1
)

:: Check of Python beschikbaar is
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo   [FOUT] Python is niet gevonden.
    echo   Download het via https://python.org
    echo.
    pause
    exit /b 1
)

echo   [OK] Node.js gevonden
echo   [OK] Python gevonden
echo.

:: Start Community Solid Server op de achtergrond
echo   [1/2] Community Solid Server starten op poort 3000...
start /min "MySolido - Solid Server" cmd /c "npx @solid/community-server -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json"

:: Wacht even tot CSS is opgestart
timeout /t 3 /nobreak >nul

:: Start Flask app
echo   [2/2] MySolido interface starten op poort 5000...
start /min "MySolido - Flask" cmd /c "python app.py"

:: Wacht even tot Flask is opgestart
timeout /t 2 /nobreak >nul

:: Open de browser
echo.
echo   MySolido is gestart!
echo   Je browser wordt geopend...
echo.
start http://localhost:5000

echo   ┌─────────────────────────────────────────┐
echo   │  MySolido draait op http://localhost:5000 │
echo   │  Sluit dit venster NIET — dat stopt alles │
echo   │  Druk op een toets om MySolido te stoppen │
echo   └─────────────────────────────────────────┘
echo.
pause >nul

:: Stop beide servers
echo.
echo   MySolido wordt gestopt...
taskkill /fi "windowtitle eq MySolido - Solid Server" /f >nul 2>nul
taskkill /fi "windowtitle eq MySolido - Flask" /f >nul 2>nul
echo   Tot de volgende keer!
timeout /t 2 /nobreak >nul
