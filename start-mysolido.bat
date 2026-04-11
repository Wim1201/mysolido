@echo off
title MySolido — Jouw persoonlijke datakluis
color 0A
cd /d "%~dp0"
set "PYTHONPATH=%~dp0"

:: Voeg lokale node en python toe aan PATH
set "PATH=%~dp0node;%~dp0python;%~dp0python\Scripts;%~dp0node_modules\.bin;%PATH%"

echo.
echo   ============================================
echo     MySolido — Jouw persoonlijke datakluis
echo   ============================================
echo.
echo   Even geduld, MySolido wordt gestart...
echo.

:: Check of lokale node bestaat, anders systeem-node
if exist "%~dp0node\node.exe" (
    set "NODE_CMD=%~dp0node\node.exe"
    set "NPX_CMD=%~dp0node\npx.cmd"
) else (
    where node >nul 2>nul
    if errorlevel 1 (
        echo   [FOUT] Node.js is niet gevonden.
        echo   Installeer MySolido opnieuw of installeer Node.js via https://nodejs.org
        echo.
        pause
        exit /b 1
    )
    set "NODE_CMD=node"
    set "NPX_CMD=npx"
)

:: Check of lokale python bestaat, anders systeem-python
if exist "%~dp0python\python.exe" (
    set "PYTHON_CMD=%~dp0python\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo   [FOUT] Python is niet gevonden.
        echo   Installeer MySolido opnieuw of installeer Python via https://python.org
        echo.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
)

:: Check of MySolido al draait
netstat -ano | findstr "127.0.0.1:5000" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo   MySolido draait al. Browser wordt geopend...
    start http://localhost:5000
    exit /b 0
)

:: Zorg dat npm global map bestaat
if not exist "%APPDATA%\npm" mkdir "%APPDATA%\npm"

:: Check of node_modules bestaat
if not exist "node_modules" (
    echo   [1/3] Community Solid Server installeren...
    echo         Dit kan een paar minuten duren bij de eerste keer.
    call %NPX_CMD% --yes @solid/community-server@7.1.9 -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json
    echo.
)

:: Start CSS op de achtergrond
echo   [1/2] Solid Server starten...
start /b "" cmd /c "%NPX_CMD% --yes @solid/community-server@7.1.9 -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json > css.log 2>&1"

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
start /b "" cmd /c "%PYTHON_CMD% app.py > flask.log 2>&1"

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

:: Eerste-keer setup: standaardmappen aanmaken als pod nog leeg is
if not exist ".data\mysolido" (
    echo   [SETUP] Eerste keer — standaardmappen aanmaken...
    powershell -command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:5000/init-folders' -UseBasicParsing -TimeoutSec 15 | Out-Null } catch {}" >nul 2>nul
    timeout /t 3 /nobreak >nul
)

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
