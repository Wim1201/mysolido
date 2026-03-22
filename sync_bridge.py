#!/usr/bin/env python3
"""
Synchroniseer de lokale MySolido pod naar de Bridge.
Eén richting: lokaal → Bridge. Gebruikt scp over SSH.
"""

import subprocess
import os
import sys
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BRIDGE_HOST = os.getenv('BRIDGE_HOST', '')
BRIDGE_PATH = os.getenv('BRIDGE_PATH', '/home/bridge/.data/')
BRIDGE_SSH_KEY = os.path.expanduser(os.getenv('BRIDGE_SSH_KEY', '~/.ssh/id_ed25519'))
BRIDGE_AUTO_SYNC = os.getenv('BRIDGE_AUTO_SYNC', 'false').lower() == 'true'

# Sync status (thread-safe)
_sync_status = {
    'running': False,
    'last_sync': None,
    'last_result': None,
    'error': None
}
_sync_lock = threading.Lock()


def is_configured():
    """Check of Bridge sync is geconfigureerd"""
    return bool(BRIDGE_HOST) and os.path.isfile(BRIDGE_SSH_KEY)


def get_status():
    """Haal de huidige sync-status op"""
    with _sync_lock:
        return dict(_sync_status)


def get_pod_data_path():
    """Haal het pad naar de lokale pod data op"""
    pod_url = os.getenv('SOLID_POD_URL', '')
    if not pod_url:
        return None
    parts = pod_url.rstrip('/').split('/')
    pod_name = parts[-1] if parts else 'mysolido'
    data_path = os.path.join('.data', pod_name)
    if os.path.isdir(data_path):
        return data_path
    return None


def sync_to_bridge():
    """
    Synchroniseer de lokale pod naar de Bridge.
    Draait scp -r om de hele pod-map te kopiëren.
    """
    global _sync_status

    if not is_configured():
        return False, "Bridge sync is niet geconfigureerd"

    with _sync_lock:
        if _sync_status['running']:
            return False, "Sync is al bezig"
        _sync_status['running'] = True
        _sync_status['error'] = None

    try:
        pod_path = get_pod_data_path()
        if not pod_path:
            raise Exception("Pod data-map niet gevonden")

        pod_name = os.path.basename(pod_path)

        # Zorg dat de doelmap bestaat op de VPS
        mkdir_cmd = [
            'ssh',
            '-i', BRIDGE_SSH_KEY,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            BRIDGE_HOST,
            f'mkdir -p {BRIDGE_PATH}{pod_name}'
        ]
        subprocess.run(mkdir_cmd, capture_output=True, text=True, timeout=30)

        # Kopieer de pod-data naar de Bridge via scp -r
        full_cmd = [
            'scp',
            '-r',
            '-i', BRIDGE_SSH_KEY,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            pod_path,
            f'{BRIDGE_HOST}:{BRIDGE_PATH}'
        ]

        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            with _sync_lock:
                _sync_status['last_sync'] = datetime.now().isoformat()
                _sync_status['last_result'] = 'success'
                _sync_status['running'] = False
            return True, "Sync voltooid"
        else:
            error_msg = result.stderr.strip() or "Onbekende fout"
            with _sync_lock:
                _sync_status['last_result'] = 'error'
                _sync_status['error'] = error_msg
                _sync_status['running'] = False
            return False, f"Sync mislukt: {error_msg}"

    except subprocess.TimeoutExpired:
        with _sync_lock:
            _sync_status['last_result'] = 'error'
            _sync_status['error'] = "Timeout (>5 minuten)"
            _sync_status['running'] = False
        return False, "Sync timeout"

    except Exception as e:
        with _sync_lock:
            _sync_status['last_result'] = 'error'
            _sync_status['error'] = str(e)
            _sync_status['running'] = False
        return False, str(e)


def sync_in_background():
    """Start sync in een achtergrond-thread"""
    if not is_configured():
        return

    thread = threading.Thread(target=sync_to_bridge, daemon=True)
    thread.start()


def auto_sync_after_change():
    """Trigger automatische sync als BRIDGE_AUTO_SYNC aan staat"""
    if BRIDGE_AUTO_SYNC and is_configured():
        def delayed_sync():
            time.sleep(2)
            sync_to_bridge()

        thread = threading.Thread(target=delayed_sync, daemon=True)
        thread.start()


if __name__ == '__main__':
    if not is_configured():
        print("FOUT: Bridge sync is niet geconfigureerd.")
        print("Stel BRIDGE_HOST en BRIDGE_SSH_KEY in je .env bestand in.")
        sys.exit(1)
    success, msg = sync_to_bridge()
    print(msg)
    sys.exit(0 if success else 1)
