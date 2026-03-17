@echo off
setlocal enabledelayedexpansion
set "ORIG_PATH=!PATH!"
chcp 65001 >nul 2>nul

:: Debug log zodat we kunnen zien of het script start
echo MySolido Installatie gestart... > "%TEMP%\mysolido-install.log"
echo Werkdirectory: %cd% >> "%TEMP%\mysolido-install.log"
echo Script locatie: %~dp0 >> "%TEMP%\mysolido-install.log"
echo Datum: %date% %time% >> "%TEMP%\mysolido-install.log"

title MySolido -- Installatie
color 0A

echo.
echo   =============================================
echo   *                                           *
echo   *              M y S o l i d o              *
echo   *                                           *
echo   *   Jouw persoonlijke datakluis op je pc     *
echo   *                                           *
echo   =============================================
echo.

:: -----------------------------------------------------
:: Check admin rechten
:: -----------------------------------------------------
:: Werkdirectory forceren
cd /d "%~dp0"

:: Forceer werkdirectory (ook als we al admin zijn)
cd /d "%~dp0"
echo Na elevation - werkdirectory: %cd% >> "%TEMP%\mysolido-install.log"

:: -----------------------------------------------------
:: Variabelen
:: -----------------------------------------------------
set "INSTALL_DIR=%USERPROFILE%\MySolido"
set "ALREADY_INSTALLED=0"
set "STEPS_TOTAL=6"

if exist "%INSTALL_DIR%\app.py" (
    set "ALREADY_INSTALLED=1"
    set "STEPS_TOTAL=3"
)

:: ==========================================================
:: STAP 1: Node.js controleren
:: ==========================================================
if "!ALREADY_INSTALLED!"=="1" (
    echo   [1/3] Node.js controleren...
) else (
    echo   [1/6] Node.js controleren...
)

where node >nul 2>nul
if !errorlevel! equ 0 (
    for /f "tokens=*" %%v in ('node --version') do echo   [OK] Node.js gevonden: %%v
    goto :node_ok
)

:: Node.js niet gevonden - downloaden en installeren
echo   Node.js niet gevonden. Wordt gedownload en geinstalleerd...
echo.
echo   Downloaden van nodejs.org...
curl -L -o "%TEMP%\node-installer.msi" https://nodejs.org/dist/v20.11.1/node-v20.11.1-x64.msi
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Download van Node.js mislukt.
    echo   Download het handmatig via: https://nodejs.org
    echo   Installeer het en voer dit script opnieuw uit.
    echo.
    goto :cleanup
)
echo   Installeren... ^(dit kan even duren^)
msiexec /i "%TEMP%\node-installer.msi" /qn
set "PATH=C:\Program Files\nodejs;!ORIG_PATH!"
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Installatie van Node.js mislukt.
    echo   Download en installeer het handmatig via: https://nodejs.org
    echo.
    goto :cleanup
)

:: Wacht tot Node.js installatie klaar is (max 120 seconden)
echo   Wachten tot installatie voltooid is...
set /a counter=0
:waitnode
:: Fallback: voeg standaard installatiepaden toe
set "PATH=C:\Program Files\nodejs;!ORIG_PATH!"

if exist "C:\Program Files\nodejs\node.exe" goto :nodedone
powershell -command "Start-Sleep -Seconds 5"
set /a counter+=5
if !counter! geq 120 (
    echo   [FOUT] Node.js installatie duurt te lang.
    goto :cleanup
)
echo   Wachten op Node.js... !counter! seconden
goto :waitnode

:nodedone
del "%TEMP%\node-installer.msi" >nul 2>nul
set "PATH=C:\Program Files\nodejs;!ORIG_PATH!"
echo   [OK] Node.js geinstalleerd
"C:\Program Files\nodejs\node.exe" --version

:node_ok

:: ==========================================================
:: STAP 2: Python controleren
:: ==========================================================
if "!ALREADY_INSTALLED!"=="1" (
    echo   [2/3] Python controleren...
) else (
    echo   [2/6] Python controleren...
)

where python >nul 2>nul
if !errorlevel! equ 0 (
    for /f "tokens=*" %%v in ('python --version') do echo   [OK] Python gevonden: %%v
    goto :python_ok
)

:: Python niet gevonden - downloaden en installeren
echo   Python niet gevonden. Wordt gedownload en geinstalleerd...
echo.
echo   Downloaden van python.org...
curl -L -o "%TEMP%\python-installer.exe" https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Download van Python mislukt.
    echo   Download het handmatig via: https://python.org
    echo   Installeer het en voer dit script opnieuw uit.
    echo.
    goto :cleanup
)
echo   Installeren... ^(dit kan even duren^)
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;C:\Program Files\nodejs;!ORIG_PATH!"
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Installatie van Python mislukt.
    echo   Download en installeer het handmatig via: https://python.org
    echo.
    goto :cleanup
)
del "%TEMP%\python-installer.exe" >nul 2>nul

if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" goto :pythondone
echo   [FOUT] Python installatie lijkt niet gelukt.
echo   Installeer handmatig via https://python.org
goto :cleanup

:pythondone
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;C:\Program Files\nodejs;!ORIG_PATH!"
echo   [OK] Python geinstalleerd
"%LOCALAPPDATA%\Programs\Python\Python311\python.exe" --version

:python_ok

:: ==========================================================
:: STAP 3: MySolido downloaden (skip als al geinstalleerd)
:: ==========================================================
if "!ALREADY_INSTALLED!"=="1" (
    echo   [3/3] MySolido is al geinstalleerd, starten...
    echo.
    goto :start_mysolido
)

echo   [3/6] MySolido downloaden...

if exist "%INSTALL_DIR%\app.py" (
    echo   [OK] MySolido al aanwezig in %INSTALL_DIR%
    goto :install_deps
)

:: Probeer git clone, anders download ZIP
where git >nul 2>nul
if !errorlevel! equ 0 (
    echo   Git gevonden, repository wordt gekloond...
    git clone https://github.com/Wim1201/mysolido.git "%INSTALL_DIR%"
    if !errorlevel! neq 0 (
        echo   [FOUT] Git clone mislukt. ZIP-download wordt geprobeerd...
        goto :download_zip
    )
    echo   [OK] MySolido gedownload via Git
    goto :install_deps
)

:download_zip
echo   Downloaden als ZIP van GitHub...
curl -L -o "%TEMP%\mysolido.zip" https://github.com/Wim1201/mysolido/archive/refs/heads/main.zip
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Download van MySolido mislukt.
    echo   Controleer je internetverbinding en probeer het opnieuw.
    echo   Of download handmatig: https://github.com/Wim1201/mysolido
    echo.
    goto :cleanup
)
echo   Uitpakken...
powershell -command "Expand-Archive -Path '%TEMP%\mysolido.zip' -DestinationPath '%TEMP%\mysolido-extract' -Force"
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Uitpakken mislukt.
    echo.
    goto :cleanup
)
:: Verplaats naar juiste locatie
if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"
move "%TEMP%\mysolido-extract\mysolido-main" "%INSTALL_DIR%" >nul
rmdir /s /q "%TEMP%\mysolido-extract" >nul 2>nul
del "%TEMP%\mysolido.zip" >nul 2>nul
echo   [OK] MySolido gedownload en uitgepakt

:: ==========================================================
:: STAP 4: Python dependencies installeren
:: ==========================================================
:install_deps
echo   [4/6] Python dependencies installeren...
cd /d "%INSTALL_DIR%"
python -m pip install -r requirements.txt --quiet
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Python dependencies konden niet worden geinstalleerd.
    echo   Probeer handmatig: python -m pip install -r requirements.txt
    echo.
    goto :cleanup
)
echo   [OK] Python dependencies geinstalleerd

:: ==========================================================
:: STAP 5: Node.js dependencies installeren
:: ==========================================================
echo   [5/6] Community Solid Server installeren...
cd /d "%INSTALL_DIR%"
call npm install @solid/community-server --quiet
if !errorlevel! neq 0 (
    echo.
    echo   [FOUT] Community Solid Server kon niet worden geinstalleerd.
    echo   Probeer handmatig: npm install @solid/community-server
    echo.
    goto :cleanup
)
echo   [OK] Community Solid Server geinstalleerd

:: ==========================================================
:: STAP 5.5: Bureaublad-snelkoppeling aanmaken
:: ==========================================================
echo   Bureaublad-snelkoppeling aanmaken...
set "ICON_PATH=%INSTALL_DIR%\static\icon.ico"
if not exist "!ICON_PATH!" set "ICON_PATH="
if defined ICON_PATH (
    powershell -command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\MySolido.lnk'); $sc.TargetPath = '%INSTALL_DIR%\start-mysolido.bat'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.IconLocation = '!ICON_PATH!'; $sc.Description = 'Jouw persoonlijke datakluis'; $sc.Save()"
) else (
    powershell -command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%USERPROFILE%\Desktop\MySolido.lnk'); $sc.TargetPath = '%INSTALL_DIR%\start-mysolido.bat'; $sc.WorkingDirectory = '%INSTALL_DIR%'; $sc.Description = 'Jouw persoonlijke datakluis'; $sc.Save()"
)
echo   [OK] Snelkoppeling aangemaakt op je bureaublad

:: ==========================================================
:: STAP 6: MySolido starten
:: ==========================================================
:start_mysolido
cd /d "%INSTALL_DIR%"

if "!ALREADY_INSTALLED!"=="0" (
    echo   [6/6] MySolido starten...
) else (
    echo   MySolido starten...
)
echo.

:: Check of poort 3000 al in gebruik is
netstat -an | findstr ":3000 " | findstr "LISTENING" >nul 2>nul
if !errorlevel! equ 0 (
    echo   [LET OP] Poort 3000 is al in gebruik.
    echo   Mogelijk draait MySolido al, of een ander programma gebruikt deze poort.
    echo   Sluit dat programma eerst, of herstart je computer.
    echo.
    goto :end
)

:: Check of poort 5000 al in gebruik is
netstat -an | findstr ":5000 " | findstr "LISTENING" >nul 2>nul
if !errorlevel! equ 0 (
    echo   [LET OP] Poort 5000 is al in gebruik.
    echo   Mogelijk draait MySolido al, of een ander programma gebruikt deze poort.
    echo   Sluit dat programma eerst, of herstart je computer.
    echo.
    goto :end
)

echo.
echo   Let op: Windows Firewall kan om toestemming vragen.
echo   Klik op 'Toegang toestaan' als dat verschijnt.
echo.

:: Start Community Solid Server op de achtergrond
echo   Community Solid Server starten op poort 3000...
start /min "MySolido - Solid Server" cmd /c "npx @solid/community-server -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json"

:: Wacht op CSS
powershell -command "Start-Sleep -Seconds 5"

:: Start Flask app
echo   MySolido interface starten op poort 5000...
start /min "MySolido - Flask" cmd /c "python app.py"

:: Wacht op Flask
powershell -command "Start-Sleep -Seconds 3"

:: Open browser
echo.
echo   =============================================
echo   *                                           *
echo   *   MySolido is klaar! Je browser wordt     *
echo   *   geopend.                                *
echo   *                                           *
echo   =============================================
echo.
start "" "http://localhost:5000"

echo   +---------------------------------------------+
echo   |  MySolido draait op http://localhost:5000     |
echo   |  Sluit dit venster NIET -- dat stopt alles    |
echo   |  Druk op een toets om MySolido te stoppen     |
echo   +---------------------------------------------+
echo.
pause >nul

:: Stop beide servers
echo.
echo   MySolido wordt gestopt...
taskkill /fi "windowtitle eq MySolido - Solid Server" /f >nul 2>nul
taskkill /fi "windowtitle eq MySolido - Flask" /f >nul 2>nul
echo   Tot de volgende keer!
powershell -command "Start-Sleep -Seconds 2"
goto :end

:: ==========================================================
:: Cleanup: temp-bestanden opruimen bij fouten
:: ==========================================================
:cleanup
if exist "%TEMP%\node-installer.msi" del "%TEMP%\node-installer.msi"
if exist "%TEMP%\python-installer.exe" del "%TEMP%\python-installer.exe"
if exist "%TEMP%\mysolido.zip" del "%TEMP%\mysolido.zip"
echo.
echo   Er is iets misgegaan. Bekijk de meldingen hierboven.

:: ==========================================================
:: Einde: venster blijft ALTIJD open
:: ==========================================================
endlocal
:end
echo.
echo   Druk op een toets om te sluiten...
pause >nul
exit /b
