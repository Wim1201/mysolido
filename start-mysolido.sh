#!/bin/bash
# MySolido Launcher for macOS
# Starts Community Solid Server and Flask app

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================"
echo "        M y S o l i d o"
echo "  Jouw persoonlijke datakluis"
echo "======================================"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo ""
    echo "[FOUT] Node.js is niet geinstalleerd."
    echo "Installeer via: https://nodejs.org (LTS versie)"
    echo "Of via Homebrew: brew install node"
    echo ""
    read -p "Druk op Enter om af te sluiten..."
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "[FOUT] Python 3 is niet geinstalleerd."
    echo "Installeer via: https://python.org"
    echo "Of via Homebrew: brew install python"
    echo ""
    read -p "Druk op Enter om af te sluiten..."
    exit 1
fi

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "[1/4] Node modules installeren..."
    npm install
else
    echo "[1/4] Node modules aanwezig"
fi

if ! python3 -c "import flask" &> /dev/null; then
    echo "[2/4] Python dependencies installeren..."
    pip3 install -r requirements.txt
else
    echo "[2/4] Python dependencies aanwezig"
fi

# Start CSS in background
echo "[3/4] Community Solid Server starten..."
npx @solid/community-server@7.1.8 \
    -p 3000 \
    -b http://127.0.0.1:3000 \
    -f .data/ \
    -c @css:config/file.json &
CSS_PID=$!

# Wait for CSS to be ready
echo "Wachten op CSS..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:3000/ > /dev/null 2>&1; then
        echo "[OK] CSS draait op poort 3000"
        break
    fi
    sleep 1
done

# Start Flask
echo "[4/4] MySolido starten..."
python3 app.py &
FLASK_PID=$!

# Wait for Flask
sleep 3
echo ""
echo "======================================"
echo "  MySolido draait!"
echo "  Open: http://localhost:5000"
echo "======================================"
echo ""
echo "Druk Ctrl+C om te stoppen."

# Open browser
open http://localhost:5000

# Wait and cleanup on exit
trap "echo 'MySolido stoppen...'; kill $CSS_PID $FLASK_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
