@echo off
chcp 65001 >nul
title MySolido

echo.
echo   === MySolido ===
echo   Jouw persoonlijke datakluis
echo.

REM Controleer of Node.js beschikbaar is
where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [FOUT] Node.js is niet gevonden.
    echo   Installeer Node.js via https://nodejs.org
    pause
    exit /b 1
)

REM Controleer of Python beschikbaar is
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo   [FOUT] Python is niet gevonden.
    echo   Installeer Python via https://python.org
    pause
    exit /b 1
)

REM Controleer of MySolido al draait
netstat -ano | findstr ":5000" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   MySolido draait al. Browser wordt geopend...
    start http://localhost:5000
    exit /b 0
)

REM Ga naar de projectmap
cd /d "%~dp0"

REM Start CSS onzichtbaar op de achtergrond
echo   Community Solid Server starten...
start /b "" cmd /c "npx @solid/community-server -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json > css.log 2>&1"

REM Wacht tot CSS bereikbaar is (max 30 pogingen van 1 seconde)
set /a attempts=0
:wait_css
set /a attempts+=1
if %attempts% gtr 30 (
    echo   [FOUT] CSS start niet op. Controleer css.log voor details.
    pause
    exit /b 1
)
curl -s -o nul http://localhost:3000 2>nul
if %ERRORLEVEL% neq 0 (
    echo   Wachten op Solid Server... (%attempts%/30)
    timeout /t 1 /nobreak >nul
    goto wait_css
)
echo   [OK] Solid Server draait

REM Start Flask onzichtbaar op de achtergrond
echo   MySolido starten...
start /b "" cmd /c "python app.py > flask.log 2>&1"

REM Wacht tot Flask bereikbaar is (max 15 pogingen)
set /a attempts=0
:wait_flask
set /a attempts+=1
if %attempts% gtr 15 (
    echo   [FOUT] MySolido start niet op. Controleer flask.log voor details.
    pause
    exit /b 1
)
curl -s -o nul http://localhost:5000 2>nul
if %ERRORLEVEL% neq 0 (
    timeout /t 1 /nobreak >nul
    goto wait_flask
)
echo   [OK] MySolido draait

echo.
echo   Browser wordt geopend...
start http://localhost:5000

echo.
echo   ================================
echo   MySolido is actief!
echo   Sluit dit venster NIET.
echo   Gebruik stop-mysolido.bat om te stoppen.
echo   ================================
echo.

REM Houd het venster open
pause >nul
