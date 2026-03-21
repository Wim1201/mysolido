#!/usr/bin/env python3
"""
Synchroniseer de lokale MySolido pod naar de Bridge.
Eén richting: lokaal → Bridge. Gebruikt rsync over SSH.

Gebruik:
    python sync_bridge.py

Configuratie via .env:
    BRIDGE_HOST=bridge@<VPS-IP>
    BRIDGE_PATH=/home/bridge/mysolido/.data/
"""

import subprocess
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BRIDGE_HOST = os.getenv('BRIDGE_HOST', '')
BRIDGE_PATH = os.getenv('BRIDGE_PATH', '/home/bridge/mysolido/.data/')
LOCAL_DATA = '.data/'
SSH_KEY = os.path.expanduser('~/.ssh/id_ed25519')


def check_config():
    """Controleer of de configuratie compleet is"""
    if not BRIDGE_HOST:
        print("FOUT: BRIDGE_HOST is niet ingesteld in .env")
        print("Voorbeeld: BRIDGE_HOST=bridge@123.45.67.89")
        sys.exit(1)

    if not os.path.isdir(LOCAL_DATA):
        print(f"FOUT: Lokale data-map '{LOCAL_DATA}' niet gevonden")
        sys.exit(1)

    if not os.path.isfile(SSH_KEY):
        print(f"FOUT: SSH-sleutel niet gevonden op {SSH_KEY}")
        print("Maak een sleutel aan met: ssh-keygen -t ed25519 -C 'mysolido-bridge'")
        sys.exit(1)


def sync():
    """Synchroniseer lokale .data/ naar de Bridge"""
    check_config()

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Synchroniseren naar {BRIDGE_HOST}...")

    cmd = [
        'rsync',
        '-avz',                    # archive, verbose, compress
        '--delete',                # verwijder bestanden op Bridge die lokaal niet meer bestaan
        '--exclude', '.mysolido/share_links.json',  # deellinks niet overschrijven
        '-e', f'ssh -i {SSH_KEY} -o StrictHostKeyChecking=no',
        LOCAL_DATA,
        f'{BRIDGE_HOST}:{BRIDGE_PATH}'
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Sync voltooid!")
            # Toon samenvatting
            lines = result.stdout.strip().split('\n')
            file_count = sum(1 for l in lines if not l.endswith('/') and not l.startswith('sending') and not l.startswith('sent') and not l.startswith('total') and l.strip())
            print(f"  Bestanden gesynchroniseerd: {file_count}")
        else:
            print(f"FOUT bij sync:")
            print(result.stderr)
            sys.exit(1)

    except FileNotFoundError:
        print("FOUT: rsync is niet geïnstalleerd.")
        print("Installeer rsync of gebruik Git Bash (bevat rsync).")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("FOUT: Sync duurde te lang (timeout na 5 minuten)")
        sys.exit(1)


if __name__ == '__main__':
    sync()
