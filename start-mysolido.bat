@echo off
title MySolido — Jouw persoonlijke datakluis
color 0A
cd /d "%~dp0"

echo.
echo   ============================================
echo     MySolido — Jouw persoonlijke datakluis
echo   ============================================
echo.
echo   Even geduld, MySolido wordt gestart...
echo.

:: Check of node beschikbaar is
where node >nul 2>nul
if errorlevel 1 (
    echo   [FOUT] Node.js is niet gevonden.
    echo   Installeer Node.js via https://nodejs.org
    echo.
    pause
    exit /b 1
)

:: Check of python beschikbaar is
where python >nul 2>nul
if errorlevel 1 (
    echo   [FOUT] Python is niet gevonden.
    echo   Installeer Python via https://python.org
    echo.
    pause
    exit /b 1
)

:: Check of MySolido al draait
netstat -ano | findstr "127.0.0.1:5000" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   MySolido draait al. Browser wordt geopend...
    start netstat -ano | findstr "127.0.0.1:5000"
    exit /b 0
)

:: Zorg dat npm global map bestaat
if not exist "%APPDATA%\npm" mkdir "%APPDATA%\npm"

:: Check of node_modules bestaat
if not exist "node_modules" (
    echo   [1/3] Community Solid Server installeren...
    echo         Dit kan een paar minuten duren bij de eerste keer.
    npm install @solid/community-server
    echo.
)

:: Start CSS op de achtergrond
echo   [1/2] Solid Server starten...
start /b "" cmd /c "npx --yes @solid/community-server@7.1.8 -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json > css.log 2>&1"

:: Wacht tot CSS bereikbaar is (max 60 pogingen van 1 seconde)
set /a attempts=0
:wait_css
set /a attempts+=1
if %attempts% gtr 60 (
    echo   [FOUT] CSS start niet op. Controleer css.log voor details.
    pause
    exit /b 1
)
powershell -command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>nul
if %ERRORLEVEL% equ 0 goto :css_running
echo   Wachten op Solid Server... (%attempts%/60)
timeout /t 1 /nobreak >nul
goto :wait_css

:css_running
echo   [OK] Solid Server draait

:: Start Flask op de achtergrond
echo   [2/2] MySolido starten...
start /b "" cmd /c "python app.py > flask.log 2>&1"

:: Wacht tot Flask bereikbaar is (max 30 pogingen)
set /a attempts=0
:wait_flask
set /a attempts+=1
if %attempts% gtr 30 (
    echo   [FOUT] MySolido start niet op. Controleer flask.log voor details.
    pause
    exit /b 1
)
powershell -command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5000' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>nul
if %ERRORLEVEL% equ 0 goto :flask_running
echo   Wachten op MySolido... (%attempts%/30)
timeout /t 1 /nobreak >nul
goto :wait_flask

:flask_running
echo   [OK] MySolido draait
echo.

:: Open browser
echo   Browser wordt geopend...
start http://localhost:5000

echo.
echo   ============================================
echo     MySolido is bereikbaar op:
echo     http://localhost:5000
echo   ============================================
echo.
echo   Dit venster openlaten! Sluiten = MySolido stopt.
echo   Gebruik stop-mysolido.bat om te stoppen.
echo.

:: Houd het venster open
pause >nul
