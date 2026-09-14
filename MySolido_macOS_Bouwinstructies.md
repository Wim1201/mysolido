# MySolido macOS Installer — Bouwinstructies

## Doel

Bouw een `MySolido-Installer.dmg` die **alles meebundelt**: Node.js, Python, en alle MySolido-bestanden. De eindgebruiker hoeft niets zelf te installeren — dubbelklik en het werkt.

## Huidige situatie

- De broncode staat op: https://github.com/Wim1201/mysolido
- Er is al een werkend `start-mysolido.sh` script in de repo
- Het huidige probleem: de .dmg verwacht dat Node.js en Python al geïnstalleerd zijn op de Mac. Niet-technische gebruikers lopen hier vast.
- De Windows-installer (`MySolido-Setup.exe`) lost dit op door Node.js en Python automatisch te downloaden bij installatie. Op macOS willen we ze meebundelen in de .app.

## Wat er gebouwd moet worden

Een `MySolido.app` bundel die bevat:

```
MySolido.app/
  Contents/
    MacOS/
      start-mysolido          ← launcher (shell script, executable)
    Resources/
      app/                    ← MySolido bronbestanden
        app.py
        translations.py
        ai_service.py
        audit.py
        shares.py
        share_links.py
        notifications.py
        trash.py
        sync_bridge.py
        watermark.py
        requirements.txt
        package.json
        .env.example
        templates/             ← alle templates
        static/                ← CSS en JS
        start-mysolido.sh
        stop-mysolido.sh
      node/                   ← Node.js standalone binary
        bin/
          node
          npm
          npx
        lib/
          ...
      python/                 ← Python standalone
        bin/
          python3
          pip3
        lib/
          ...
      mysolido.icns           ← app-icoon
    Info.plist
```

## Stap-voor-stap

### 1. Vereisten op de bouw-Mac

- macOS 12+ (Monterey of nieuwer)
- Xcode Command Line Tools: `xcode-select --install`
- Git: `git --version`
- create-dmg (optioneel, voor mooie .dmg): `brew install create-dmg`

### 2. Clone de repo

```bash
git clone https://github.com/Wim1201/mysolido.git
cd mysolido
```

### 3. Download Node.js standalone

Download de macOS ARM64 binary (voor Apple Silicon) en x64 (voor Intel). Kies LTS:

```bash
# Apple Silicon (M1/M2/M3)
curl -O https://nodejs.org/dist/v20.18.1/node-v20.18.1-darwin-arm64.tar.gz
tar xzf node-v20.18.1-darwin-arm64.tar.gz
mv node-v20.18.1-darwin-arm64 node-arm64

# Intel
curl -O https://nodejs.org/dist/v20.18.1/node-v20.18.1-darwin-x64.tar.gz
tar xzf node-v20.18.1-darwin-x64.tar.gz
mv node-v20.18.1-darwin-x64 node-x64
```

Kies de juiste architectuur voor de doelgroep, of bouw twee versies.

### 4. Download Python standalone

Gebruik python-build-standalone (geen installatie nodig):

```bash
# Apple Silicon
curl -LO https://github.com/indygreg/python-build-standalone/releases/download/20240107/cpython-3.12.1+20240107-aarch64-apple-darwin-install_only.tar.gz
tar xzf cpython-3.12.1+20240107-aarch64-apple-darwin-install_only.tar.gz
mv python python-arm64

# Intel
curl -LO https://github.com/indygreg/python-build-standalone/releases/download/20240107/cpython-3.12.1+20240107-x86_64-apple-darwin-install_only.tar.gz
tar xzf cpython-3.12.1+20240107-x86_64-apple-darwin-install_only.tar.gz
mv python python-x64
```

### 5. Installeer Python dependencies vooraf

```bash
# Gebruik de gebundelde Python
./python-arm64/bin/python3 -m pip install -r requirements.txt --target=python-arm64/lib/python3.12/site-packages/
```

### 6. Installeer Community Solid Server vooraf

```bash
# Gebruik de gebundelde Node; de CSS-versie (7.2.0) staat in package.json
export PATH="$(pwd)/node-arm64/bin:$PATH"
npm install
```

De `node_modules/` map moet mee in de .app bundel.

### 7. Maak het launcher-script

Maak `start-mysolido` (zonder extensie, executable):

```bash
#!/bin/bash
# MySolido Launcher — macOS
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
APP_DIR="$DIR/app"
NODE_DIR="$DIR/node"
PYTHON_DIR="$DIR/python"

export PATH="$NODE_DIR/bin:$PYTHON_DIR/bin:$PATH"
export PYTHONPATH="$APP_DIR"

cd "$APP_DIR"

# Start CSS op de achtergrond vanuit node_modules (versie uit package.json)
"$NODE_DIR/bin/node" node_modules/@solid/community-server/bin/server.js \
  -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json &
CSS_PID=$!

# Wacht tot CSS draait
for i in $(seq 1 60); do
  curl -s http://127.0.0.1:3000 > /dev/null 2>&1 && break
  sleep 1
done

# Start Flask
"$PYTHON_DIR/bin/python3" app.py &
FLASK_PID=$!

# Wacht tot Flask draait
for i in $(seq 1 30); do
  curl -s http://127.0.0.1:5000 > /dev/null 2>&1 && break
  sleep 1
done

# Eerste-keer setup
if [ ! -d ".data/mysolido" ]; then
  curl -s http://127.0.0.1:5000/init-folders > /dev/null 2>&1
  sleep 2
fi

# Open browser
open http://localhost:5000

# Wacht tot processen stoppen
wait $CSS_PID $FLASK_PID
```

Maak executable: `chmod +x start-mysolido`

### 8. Maak Info.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>MySolido</string>
    <key>CFBundleDisplayName</key>
    <string>MySolido</string>
    <key>CFBundleIdentifier</key>
    <string>com.mysolido.app</string>
    <key>CFBundleVersion</key>
    <string>1.3.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.3.0</string>
    <key>CFBundleExecutable</key>
    <string>start-mysolido</string>
    <key>CFBundleIconFile</key>
    <string>mysolido</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
```

### 9. Bouw de .app bundel

```bash
# Maak de structuur
mkdir -p MySolido.app/Contents/MacOS
mkdir -p MySolido.app/Contents/Resources/app
mkdir -p MySolido.app/Contents/Resources/node
mkdir -p MySolido.app/Contents/Resources/python

# Kopieer launcher
cp start-mysolido MySolido.app/Contents/MacOS/
chmod +x MySolido.app/Contents/MacOS/start-mysolido

# Kopieer Info.plist
cp Info.plist MySolido.app/Contents/

# Kopieer Node.js
cp -R node-arm64/* MySolido.app/Contents/Resources/node/

# Kopieer Python
cp -R python-arm64/* MySolido.app/Contents/Resources/python/

# Kopieer MySolido bestanden
cp app.py translations.py ai_service.py audit.py shares.py \
   share_links.py notifications.py trash.py sync_bridge.py \
   watermark.py requirements.txt package.json .env.example \
   MySolido.app/Contents/Resources/app/

cp -R templates MySolido.app/Contents/Resources/app/
cp -R static MySolido.app/Contents/Resources/app/
cp -R node_modules MySolido.app/Contents/Resources/app/

# Kopieer icoon (als .icns beschikbaar is)
# cp mysolido.icns MySolido.app/Contents/Resources/
```

### 10. Maak de .dmg

```bash
# Simpele methode
hdiutil create -volname "MySolido" -srcfolder MySolido.app -ov -format UDZO MySolido-Installer.dmg

# Of met create-dmg (mooier, met achtergrond):
create-dmg \
  --volname "MySolido" \
  --volicon "mysolido.icns" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon "MySolido.app" 150 200 \
  --app-drop-link 450 200 \
  MySolido-Installer.dmg \
  MySolido.app
```

### 11. Test

1. Dubbelklik op de .dmg
2. Sleep MySolido.app naar Applications
3. Dubbelklik op MySolido in Applications
4. macOS toont waarschijnlijk een waarschuwing → Rechtermuisklik → Open
5. Browser opent op http://localhost:5000
6. Controleer of het welcome-scherm verschijnt

### 12. Upload

Upload de nieuwe `MySolido-Installer.dmg` naar:
https://github.com/Wim1201/mysolido/releases/edit/v1.3.0

Verwijder eerst de oude .dmg en upload de nieuwe.

## Belangrijk

- De .data/ map (pod-opslag) moet BUITEN de .app bundel staan, anders verlies je data bij updates. Het start-script gebruikt de huidige werkmap voor .data/. Dit betekent dat de data in ~/Applications/ of waar de .app staat terecht komt. Overweeg om .data/ in ~/MySolido/ te plaatsen.
- De app is NIET gesigned (geen Apple Developer account). Gebruikers moeten rechtermuisklik → Open gebruiken bij eerste keer.
- Test op zowel Apple Silicon als Intel als je beide wilt ondersteunen.

## Geschatte grootte

- Node.js: ~50MB
- Python + dependencies: ~80MB
- MySolido + node_modules: ~30MB
- Totaal .dmg: ~100-150MB (gecomprimeerd)

## Contact

Vragen? Mail wim@mysolido.com of open een issue op GitHub.
