import re
import os
import io
import sys
import time
import secrets
import string
import zipfile
import shutil
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import unquote
from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file, session, abort
import requests
import base64
from dotenv import load_dotenv
from audit import log_action, get_audit_log
from shares import add_share, remove_share, get_all_shares, get_shares_for_resource, check_expired_shares
from trash import move_to_trash, restore_from_trash, permanent_delete, get_all_trash, cleanup_expired
from notifications import add_notification, get_all_notifications, get_unread_count, mark_as_read, mark_all_read
from share_links import (
    create_share_link, get_share_link, deactivate_share_link,
    get_active_share_links, increment_download_count, hash_password
)
from sync_bridge import (
    is_configured as bridge_sync_configured,
    get_status as get_bridge_sync_status,
    sync_in_background,
    auto_sync_after_change
)

load_dotenv()

BRIDGE_MODE = '--bridge' in sys.argv

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(hours=24)

# === CONFIGURATIE ===
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
CSS_BASE_URL = os.getenv('CSS_BASE_URL', 'http://127.0.0.1:3000')
SOLID_POD_URL = os.getenv('SOLID_POD_URL', 'http://127.0.0.1:3000/mysolido/')
WEBID = os.getenv('WEBID', 'http://127.0.0.1:3000/mysolido/profile/card#me')
OWNER_WEBID = WEBID
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_pod_data_path():
    """Bepaal het lokale filesystem pad naar de pod data"""
    pod_url = os.getenv('SOLID_POD_URL', SOLID_POD_URL or 'http://127.0.0.1:3000/mysolido/')
    pod_name = pod_url.rstrip('/').split('/')[-1]
    return os.path.join(PROJECT_DIR, '.data', pod_name)


def safe_pod_path(relative_path):
    """Geeft het veilige absolute pad terug, of None bij path traversal"""
    pod_path = get_pod_data_path()
    full_path = os.path.normpath(os.path.join(pod_path, relative_path))
    if not full_path.startswith(os.path.normpath(pod_path)):
        return None
    return full_path


def url_to_relative_path(url):
    """Converteer een pod URL naar een relatief pad binnen de pod data-map"""
    pod_url = os.getenv('SOLID_POD_URL', SOLID_POD_URL or 'http://127.0.0.1:3000/mysolido/')
    if url.startswith(pod_url):
        return unquote(url[len(pod_url):])
    css_base = os.getenv('CSS_BASE_URL', 'http://127.0.0.1:3000')
    pod_name = pod_url.rstrip('/').split('/')[-1]
    prefix = f'{css_base}/{pod_name}/'
    if url.startswith(prefix):
        return unquote(url[len(prefix):])
    return None


def pod_write(relative_path, content):
    """Schrijf naar de pod via het filesystem"""
    full_path = safe_pod_path(relative_path)
    if not full_path:
        return False
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    mode = 'wb' if isinstance(content, bytes) else 'w'
    with open(full_path, mode) as f:
        f.write(content)
    return True


def pod_delete(relative_path):
    """Verwijder uit de pod via het filesystem"""
    full_path = safe_pod_path(relative_path)
    if not full_path:
        return False
    if os.path.isdir(full_path):
        shutil.rmtree(full_path)
        return True
    elif os.path.isfile(full_path):
        os.remove(full_path)
        return True
    return False


def pod_mkdir(relative_path):
    """Maak een map aan in de pod via het filesystem"""
    full_path = safe_pod_path(relative_path)
    if not full_path:
        return False
    os.makedirs(full_path, exist_ok=True)
    return True


def pod_exists(relative_path):
    """Check of een pad bestaat in de pod"""
    full_path = safe_pod_path(relative_path)
    if not full_path:
        return False
    return os.path.exists(full_path)


def list_folder_filesystem(relative_path=''):
    """Lees de inhoud van een map van het filesystem"""
    pod_path = get_pod_data_path()
    folder_path = os.path.join(pod_path, relative_path) if relative_path else pod_path
    folder_path = os.path.normpath(folder_path)

    # Beveiligingscheck
    if not folder_path.startswith(os.path.normpath(pod_path)):
        return []

    if not os.path.isdir(folder_path):
        return []

    items = []
    pod_url = os.getenv('SOLID_POD_URL', SOLID_POD_URL or 'http://127.0.0.1:3000/mysolido/')

    for entry in os.listdir(folder_path):
        # Skip verborgen bestanden en metadata
        if entry.startswith('.'):
            continue

        full_path = os.path.join(folder_path, entry)
        entry_relative = os.path.join(relative_path, entry).replace('\\', '/') if relative_path else entry

        if os.path.isdir(full_path):
            svg = get_folder_svg(entry)
            items.append({
                'name': entry,
                'url': pod_url + entry_relative + '/',
                'is_folder': True,
                'svg': svg,
                'size': '',
                'modified': datetime.fromtimestamp(os.path.getmtime(full_path)).strftime('%d %b %Y'),
            })
        else:
            # Skip metadata bestanden
            if entry.endswith('.acl') or entry.endswith('.meta'):
                continue

            stat = os.stat(full_path)
            items.append({
                'name': entry,
                'url': pod_url + entry_relative,
                'is_folder': False,
                'svg': None,
                'size': format_size(stat.st_size),
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%d %b %Y'),
            })

    # Sorteer: mappen eerst, dan bestanden op naam
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))
    return items


def search_pod_filesystem(query, relative_path='', depth=0, max_depth=5):
    """Zoek recursief in de pod via het filesystem"""
    if depth >= max_depth:
        return []

    results = []
    pod_path = get_pod_data_path()
    search_path = os.path.join(pod_path, relative_path) if relative_path else pod_path

    if not os.path.isdir(search_path):
        return results

    pod_url = os.getenv('SOLID_POD_URL', SOLID_POD_URL or 'http://127.0.0.1:3000/mysolido/')

    for entry in os.listdir(search_path):
        if entry.startswith('.') or entry.endswith('.acl') or entry.endswith('.meta'):
            continue

        full_path = os.path.join(search_path, entry)
        entry_relative = os.path.join(relative_path, entry).replace('\\', '/') if relative_path else entry

        if os.path.isdir(full_path):
            results.extend(search_pod_filesystem(query, entry_relative, depth + 1, max_depth))
        else:
            if query.lower() in entry.lower():
                stat = os.stat(full_path)
                results.append({
                    'name': entry,
                    'url': pod_url + entry_relative,
                    'path': entry_relative,
                    'folder_path': relative_path,
                    'is_folder': False,
                    'svg': None,
                    'size': format_size(stat.st_size),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%d %b %Y'),
                })

    return results


def get_pod_stats_filesystem():
    """Bereken pod-statistieken via het filesystem"""
    pod_path = get_pod_data_path()
    total_files = 0
    total_size = 0
    total_folders = 0
    latest_modified = None

    if not os.path.isdir(pod_path):
        return {'file_count': 0, 'folder_count': 0, 'total_size': 0,
                'total_size_formatted': '0 B', 'latest_modified': None,
                'active_share_links': 0}

    for root, dirs, files in os.walk(pod_path):
        # Skip verborgen mappen en systeemmappen
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '_trash']
        total_folders += len(dirs)
        for f in files:
            if not f.startswith('.') and not f.endswith('.acl') and not f.endswith('.meta'):
                total_files += 1
                filepath = os.path.join(root, f)
                size = os.path.getsize(filepath)
                total_size += size
                mtime = os.path.getmtime(filepath)
                if latest_modified is None or mtime > latest_modified:
                    latest_modified = mtime

    active_links = len(get_active_share_links())

    return {
        'file_count': total_files,
        'folder_count': total_folders,
        'total_size': total_size,
        'total_size_formatted': format_size(total_size),
        'latest_modified': datetime.fromtimestamp(latest_modified).strftime('%d %b %Y') if latest_modified else None,
        'active_share_links': active_links
    }


def generate_password(length=16):
    """Genereer een veilig wachtwoord"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def auto_setup():
    """Automatische setup bij eerste start"""
    global CLIENT_ID, CLIENT_SECRET, CSS_BASE_URL, SOLID_POD_URL, WEBID, OWNER_WEBID
    import json

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

    # Stap 0: Check of setup nodig is
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
        if os.getenv('CLIENT_ID') and os.getenv('CLIENT_SECRET'):
            print("  [OK] Bestaande configuratie gevonden")
            return True

    print("  Eerste keer opstarten — account wordt aangemaakt...")

    css_base = 'http://127.0.0.1:3000'

    try:
        # Stap 1: Wacht tot CSS draait
        css_ready = False
        for attempt in range(30):
            try:
                r = requests.get(f'{css_base}/.account/',
                    headers={'Accept': 'application/json'},
                    timeout=3)
                if r.status_code == 200:
                    css_ready = True
                    break
            except requests.ConnectionError:
                pass
            if attempt < 29:
                time.sleep(2)

        if not css_ready:
            print("  [FOUT] Community Solid Server is niet bereikbaar op http://127.0.0.1:3000")
            return False

        initial_controls = r.json().get('controls', {})

        # Stap 2: Maak account aan
        create_url = initial_controls.get('account', {}).get('create')
        if not create_url:
            print("  [FOUT] Geen account-create URL gevonden in CSS API")
            print(f"  [DEBUG] Controls: {json.dumps(initial_controls, indent=2)}")
            return False

        r = requests.post(create_url,
            headers={'Content-Type': 'application/json'},
            json={})

        if r.status_code not in [200, 201]:
            print(f"  [FOUT] Account aanmaken mislukt")
            print(f"  [DEBUG] URL: {create_url}")
            print(f"  [DEBUG] Status: {r.status_code}")
            print(f"  [DEBUG] Response: {r.text[:500]}")
            return False

        data = r.json()
        authorization = data.get('authorization')
        if not authorization:
            print("  [FOUT] Geen authorization token ontvangen")
            print(f"  [DEBUG] Response: {r.text[:500]}")
            return False

        # Stap 3: Haal volledige controls op met authorization token
        r = requests.get(f'{css_base}/.account/',
            headers={
                'Authorization': f'CSS-Account-Token {authorization}',
                'Accept': 'application/json'
            })

        if r.status_code != 200:
            print(f"  [FOUT] Account controls ophalen mislukt")
            print(f"  [DEBUG] Status: {r.status_code}")
            print(f"  [DEBUG] Response: {r.text[:500]}")
            return False

        full_controls = r.json().get('controls', {})
        print(f"  [DEBUG] Controls: {json.dumps(full_controls, indent=2)}")

        # Stap 4: Registreer email/wachtwoord
        password_create_url = (
            full_controls.get('password', {}).get('create')
            or full_controls.get('password', {}).get('register')
            or full_controls.get('html', {}).get('password', {}).get('register')
        )
        if not password_create_url:
            print("  [FOUT] Geen password-create URL gevonden in CSS API")
            return False

        email = 'user@mysolido.local'
        password = generate_password()

        r = requests.post(password_create_url,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'CSS-Account-Token {authorization}'
            },
            json={
                'email': email,
                'password': password
            })

        if r.status_code not in [200, 201]:
            print(f"  [FOUT] Wachtwoord registreren mislukt")
            print(f"  [DEBUG] URL: {password_create_url}")
            print(f"  [DEBUG] Status: {r.status_code}")
            print(f"  [DEBUG] Response: {r.text[:500]}")
            return False

        # Stap 5: Maak pod aan
        pod_create_url = full_controls.get('account', {}).get('pod')
        if not pod_create_url:
            print("  [FOUT] Geen pod-create URL gevonden in CSS API")
            return False

        pod_name = 'mysolido'

        r = requests.post(pod_create_url,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'CSS-Account-Token {authorization}'
            },
            json={'name': pod_name})

        if r.status_code not in [200, 201]:
            print(f"  [FOUT] Pod aanmaken mislukt")
            print(f"  [DEBUG] URL: {pod_create_url}")
            print(f"  [DEBUG] Status: {r.status_code}")
            print(f"  [DEBUG] Response: {r.text[:500]}")
            return False

        pod_url = f'{css_base}/{pod_name}/'
        webid = f'{pod_url}profile/card#me'

        # Stap 6: Maak client credentials aan
        credentials_url = full_controls.get('account', {}).get('clientCredentials')
        if not credentials_url:
            print("  [FOUT] Geen clientCredentials URL gevonden in CSS API")
            return False

        r = requests.post(credentials_url,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'CSS-Account-Token {authorization}'
            },
            json={
                'name': 'mysolido-app',
                'webId': webid
            })

        if r.status_code not in [200, 201]:
            print(f"  [FOUT] Client credentials aanmaken mislukt")
            print(f"  [DEBUG] URL: {credentials_url}")
            print(f"  [DEBUG] Status: {r.status_code}")
            print(f"  [DEBUG] Response: {r.text[:500]}")
            return False

        cred_data = r.json()
        client_id = cred_data.get('id')
        client_secret = cred_data.get('secret')

        if not client_id or not client_secret:
            print("  [FOUT] Geen client credentials ontvangen")
            print(f"  [DEBUG] Response: {json.dumps(cred_data, indent=2)}")
            return False

        # Stap 7: Schrijf .env
        with open(env_path, 'w') as f:
            f.write(f'CSS_BASE_URL={css_base}\n')
            f.write(f'SOLID_POD_URL={pod_url}\n')
            f.write(f'WEBID={webid}\n')
            f.write(f'CSS_EMAIL={email}\n')
            f.write(f'CSS_PASSWORD={password}\n')
            f.write(f'CLIENT_ID={client_id}\n')
            f.write(f'CLIENT_SECRET={client_secret}\n')
            f.write('SHARE_BASE_URL=http://localhost:5000\n')
            bridge_pw = generate_password()
            f.write(f'BRIDGE_PASSWORD={bridge_pw}\n')
            f.write(f'FLASK_SECRET_KEY={secrets.token_hex(32)}\n')

        # Stap 8: Herlaad .env en update globale variabelen
        load_dotenv(env_path, override=True)
        CLIENT_ID = os.getenv('CLIENT_ID')
        CLIENT_SECRET = os.getenv('CLIENT_SECRET')
        CSS_BASE_URL = os.getenv('CSS_BASE_URL', css_base)
        SOLID_POD_URL = os.getenv('SOLID_POD_URL', pod_url)
        WEBID = os.getenv('WEBID', webid)
        OWNER_WEBID = WEBID

        print(f"  [OK] Account aangemaakt: {email}")
        print(f"  [OK] Pod aangemaakt: /{pod_name}/")
        print(f"  [OK] Credentials opgeslagen in .env")

        return True

    except Exception as e:
        print(f"  [FOUT] Setup mislukt: {e}")
        import traceback
        traceback.print_exc()
        return False

# Viewable file types for inline display
VIEWABLE_TYPES = {
    '.pdf': 'application/pdf',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.txt': 'text/plain',
    '.html': 'text/html',
    '.json': 'application/json',
    '.csv': 'text/csv',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
}

# Default folders to create on init
DEFAULT_FOLDERS = [
    'identiteit', 'medisch', 'financieel', 'wonen', 'zakelijk',
    'werk', 'voertuigen', 'juridisch', 'media', 'wachtwoorden',
    'gezin', 'abonnementen', 'inbox', 'verzekeringen',
    'huisdieren', 'opleiding', 'reizen', 'digitaal-testament',
    'persoonlijk', 'projecten',
]

# Folder icons with SVG and colors (matching mysolido.com landing page)
FOLDER_ICONS = {
    'identiteit': {
        'color': '#5b6abf',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#5b6abf" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    },
    'medisch': {
        'color': '#e05555',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#e05555" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"/></svg>'
    },
    'financieel': {
        'color': '#e8913a',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#e8913a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><circle cx="12" cy="14" r="3"/><path d="M2 7l4-4h12l4 4"/></svg>'
    },
    'wonen': {
        'color': '#d4a030',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#d4a030" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-6h6v6"/></svg>'
    },
    'zakelijk': {
        'color': '#2ea8a0',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#2ea8a0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V3H8v4"/><path d="M12 12v3"/></svg>'
    },
    'werk': {
        'color': '#4a8c5c',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#4a8c5c" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4M6.34 6.34l2.83 2.83M2 12h4M6.34 17.66l2.83-2.83"/><circle cx="12" cy="12" r="4"/></svg>'
    },
    'voertuigen': {
        'color': '#e07830',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#e07830" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/><path d="M5 17h-2V6h14l3 5v6h-3"/><path d="M9 17h6"/></svg>'
    },
    'juridisch': {
        'color': '#8868b0',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#8868b0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/></svg>'
    },
    'media': {
        'color': '#d06090',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#d06090" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/><circle cx="18" cy="6" r="1"/></svg>'
    },
    'wachtwoorden': {
        'color': '#c8a050',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#c8a050" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.78 7.78 5.5 5.5 0 017.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>'
    },
    'gezin': {
        'color': '#4a9060',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#4a9060" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>'
    },
    'abonnementen': {
        'color': '#6088c0',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#6088c0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 7h8M8 12h8M8 17h5"/></svg>'
    },
    'inbox': {
        'color': '#5090b0',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#5090b0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 9 8 12 2 12"/></svg>'
    },
    'verzekeringen': {
        'color': '#40a070',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#40a070" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>'
    },
    'huisdieren': {
        'color': '#d06050',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#d06050" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="10" r="3"/><path d="M6.17 17.34A7 7 0 0112 14a7 7 0 015.83 3.34"/><path d="M4.93 4.93a10 10 0 1014.14 0"/></svg>'
    },
    'opleiding': {
        'color': '#5080a8',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#5080a8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M4 4.5A2.5 2.5 0 016.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15z"/></svg>'
    },
    'reizen': {
        'color': '#c87840',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#c87840" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/></svg>'
    },
    'digitaal-testament': {
        'color': '#6878a8',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#6878a8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/><path d="M7 8l3 3-3 3"/></svg>'
    },
    'persoonlijk': {
        'color': '#b8a040',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#b8a040" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>'
    },
    'projecten': {
        'color': '#9068a0',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#9068a0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>'
    },
}


@app.before_request
def check_bridge_auth():
    if not BRIDGE_MODE:
        return

    public_routes = ['bridge_login', 'view_shared_file', 'static']

    if request.endpoint in public_routes:
        return

    if request.path.startswith('/share/') or request.path.startswith('/share-password/'):
        return

    if not session.get('bridge_authenticated'):
        return redirect(url_for('bridge_login'))


@app.before_request
def check_bridge_mode():
    if not BRIDGE_MODE:
        return

    blocked_endpoints = [
        'upload',
        'delete',
        'move',
        'create_folder_route',
        'share',
        'create_share_link_route',
        'revoke_share_link',
        'init_folders',
        'init_folders_welcome',
    ]

    if request.endpoint in blocked_endpoints:
        flash('Deze actie is niet beschikbaar via de Bridge. Gebruik je lokale MySolido.', 'error')
        return redirect(request.referrer or url_for('index'))


@app.context_processor
def inject_globals():
    """Inject global template variables"""
    nav_map = {
        'index': 'kluis',
        'browse': 'kluis',
        'search': 'zoeken',
        'shares_overview': 'gedeeld',
        'trash_overview': 'prullenbak',
        'audit': 'logboek',
        'profile': 'profiel',
        'settings': 'profiel',
        'notifications_page': '',
    }
    active = nav_map.get(request.endpoint, '')
    return {
        'folder_icons': FOLDER_ICONS,
        'unread_count': get_unread_count(),
        'active_nav': active,
        'bridge_mode': BRIDGE_MODE,
        'bridge_sync_configured': bridge_sync_configured(),
        'bridge_sync_status': get_bridge_sync_status(),
    }


@app.route('/bridge-login', methods=['GET', 'POST'])
def bridge_login():
    if not BRIDGE_MODE:
        return redirect(url_for('index'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        bridge_password = os.getenv('BRIDGE_PASSWORD', os.getenv('CSS_PASSWORD', ''))

        if password == bridge_password:
            session.permanent = True
            session['bridge_authenticated'] = True
            return redirect(url_for('index'))
        else:
            flash('Onjuist wachtwoord', 'error')

    return render_template('bridge_login.html')


@app.route('/bridge-logout')
def bridge_logout():
    session.pop('bridge_authenticated', None)
    return redirect(url_for('bridge_login'))


@app.route('/bridge-sync', methods=['POST'])
def trigger_bridge_sync():
    if BRIDGE_MODE:
        abort(403)

    if not bridge_sync_configured():
        flash('Bridge sync is niet geconfigureerd. Stel BRIDGE_HOST in je .env in.', 'error')
        return redirect(url_for('profile'))

    sync_in_background()
    flash('Synchronisatie gestart...', 'success')
    log_action('bridge_sync_triggered', {})
    return redirect(request.referrer or url_for('index'))


@app.route('/bridge-sync/status')
def bridge_sync_status():
    if BRIDGE_MODE:
        abort(403)
    from flask import jsonify
    return jsonify(get_bridge_sync_status())


# LEGACY: HTTP-gebaseerde functies — bewaard voor toekomstige remote pod-toegang
def get_access_token():
    """Verkrijg een access token via client credentials"""
    client_id = os.getenv('CLIENT_ID') or CLIENT_ID
    client_secret = os.getenv('CLIENT_SECRET') or CLIENT_SECRET
    css_base = os.getenv('CSS_BASE_URL', 'http://127.0.0.1:3000')

    if not client_id or not client_secret:
        return None

    auth = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    try:
        response = requests.post(
            f'{css_base}/.oidc/token',
            data={'grant_type': 'client_credentials', 'scope': 'webid'},
            headers={
                'Authorization': f'Basic {auth}',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            timeout=10
        )

        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            print(f"Token ophalen mislukt: {response.status_code} - {response.text}")
            return None
    except requests.ConnectionError:
        return None


def pod_request(method, url, **kwargs):
    """Doe een geauthenticeerde request naar de pod"""
    token = get_access_token()
    if token is None:
        return None

    # Voeg headers samen
    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f'Bearer {token}'

    if method == 'GET':
        return requests.get(url, headers=headers, **kwargs)
    elif method == 'HEAD':
        return requests.head(url, headers=headers, **kwargs)
    elif method == 'PUT':
        return requests.put(url, headers=headers, **kwargs)
    elif method == 'DELETE':
        return requests.delete(url, headers=headers, **kwargs)


def container_exists(url):
    """Check if a container (folder) already exists"""
    response = pod_request('GET', url, headers={'Accept': 'text/turtle'})
    return response is not None and response.status_code == 200


def create_container(url):
    """Create a container (folder) in the pod"""
    return pod_request('PUT', url,
        headers={
            'Content-Type': 'text/turtle',
            'Link': '<http://www.w3.org/ns/ldp#BasicContainer>; rel="type"'
        },
        data=''
    )


def get_folder_svg(folder_name):
    """Get the SVG icon for a folder"""
    name_lower = folder_name.lower()
    info = FOLDER_ICONS.get(name_lower)
    if info:
        return info['svg']
    # Generic folder icon for unknown folders
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'


# LEGACY: HTTP-gebaseerde container listing — bewaard voor toekomstige remote pod-toegang
def parse_container_contents(turtle_text, base_url):
    """Parse Turtle response to extract container contents"""
    items = []

    contains_pattern = re.compile(r'ldp:contains\s+(.+?)\.\s*$', re.DOTALL | re.MULTILINE)
    contains_matches = contains_pattern.findall(turtle_text)

    resources = []
    for match in contains_matches:
        resources.extend(re.findall(r'<([^>]+)>', match))

    for resource in resources:
        if not resource.startswith('http'):
            full_url = base_url.rstrip('/') + '/' + resource.lstrip('/')
        else:
            full_url = resource
        name = unquote(resource.rstrip('/').split('/')[-1])
        is_folder = resource.endswith('/')
        svg = get_folder_svg(name) if is_folder else None
        items.append({
            'name': name,
            'url': full_url,
            'is_folder': is_folder,
            'svg': svg,
        })
    items.sort(key=lambda x: (not x['is_folder'], x['name'].lower()))

    # Fetch metadata (size, modified) for files via HEAD requests (max 20)
    file_count = 0
    for item in items:
        if item['is_folder']:
            item['size'] = ''
            item['modified'] = ''
            continue
        file_count += 1
        if file_count <= 20:
            try:
                head = pod_request('HEAD', item['url'])
                if head and head.status_code == 200:
                    # Size
                    cl = head.headers.get('Content-Length')
                    item['size'] = format_size(int(cl)) if cl else '—'
                    # Date
                    lm = head.headers.get('Last-Modified')
                    if lm:
                        item['modified'] = format_date_nl(lm)
                    else:
                        item['modified'] = '—'
                else:
                    item['size'] = '—'
                    item['modified'] = '—'
            except Exception:
                item['size'] = '—'
                item['modified'] = '—'
        else:
            item['size'] = '—'
            item['modified'] = '—'

    return items


def build_breadcrumbs(folder_path):
    """Build breadcrumb navigation from a folder path"""
    crumbs = [{'name': 'Pod', 'path': ''}]
    if folder_path:
        parts = [p for p in folder_path.split('/') if p]
        for i, part in enumerate(parts):
            path = '/'.join(parts[:i + 1])
            crumbs.append({'name': part, 'path': path})
    return crumbs


def normalize_folder_name(name):
    """Normalize a folder name: lowercase, hyphens instead of spaces, no special chars"""
    name = name.strip().lower()
    name = name.replace(' ', '-')
    name = re.sub(r'[^a-z0-9\-]', '', name)
    name = re.sub(r'-+', '-', name).strip('-')
    return name


@app.route('/')
def index():
    """Toon de inhoud van de pod root"""
    return browse_folder('')


@app.route('/browse/<path:folder_path>')
def browse(folder_path):
    """Toon de inhoud van een map in de pod"""
    return browse_folder(folder_path)


def get_all_folders():
    """Geeft lijst van alle hoofdmappen met icoon en label voor de upload-dropdown"""
    return [
        {'name': name, 'label': name.capitalize(), 'svg': FOLDER_ICONS.get(name, {}).get('svg', ''), 'color': FOLDER_ICONS.get(name, {}).get('color', '')}
        for name in DEFAULT_FOLDERS
    ]


def get_move_folders(folder_path, items):
    """Bouw de mappenlijst voor de verplaats-dropdown"""
    folders = []
    subfolders = [item for item in items if item['is_folder']]

    for name in DEFAULT_FOLDERS:
        folders.append({'value': name, 'label': name.capitalize(), 'indent': 0})
        if folder_path == name or folder_path.startswith(name + '/'):
            for sub in subfolders:
                sub_path = folder_path + '/' + sub['name']
                folders.append({'value': sub_path, 'label': sub['name'], 'indent': 1})
    return folders


def get_recent_files(limit=5):
    """Get recent file uploads from audit log"""
    log = get_audit_log('upload', limit=limit)
    return log


def sort_items(items, sort_by):
    """Sort items: folders always first, then files by chosen criterion"""
    folders = [i for i in items if i['is_folder']]
    files = [i for i in items if not i['is_folder']]
    if sort_by == 'name-desc':
        files.sort(key=lambda x: x['name'].lower(), reverse=True)
    elif sort_by == 'date-desc':
        files.reverse()
    elif sort_by == 'date-asc':
        pass  # server order is already oldest first
    else:  # name-asc (default)
        files.sort(key=lambda x: x['name'].lower())
    return folders + files


def is_pod_empty(items):
    """Check if the pod is essentially empty (only system files like profile/, README)"""
    SYSTEM_NAMES = {'profile', 'README', '.acl', '_trash'}
    user_items = [i for i in items if i['name'] not in SYSTEM_NAMES]
    return len(user_items) == 0


def browse_folder(folder_path):
    """Shared logic for browsing a folder"""
    # Check for expired shares and auto-revoke
    expired = check_expired_shares()
    for s in expired:
        write_acl(s['resource_url'])
        display_webid = 'iedereen (openbaar)' if s['webid'] == 'public' else s['webid']
        resource_name = s['resource_url'].rstrip('/').split('/')[-1]
        flash(f'Toegang van {display_webid} tot "{resource_name}" is verlopen en ingetrokken', 'success')
        log_action('revoke_expired', {'resource': s.get('resource_path', ''), 'webid': s['webid']})
        add_notification('share_expired', f'Toegang van {display_webid} tot "{resource_name}" is verlopen')

    folder_path = folder_path.strip('/')
    sort_by = request.args.get('sort', 'name-asc')

    items = list_folder_filesystem(folder_path)

    # Show welcome page if pod root is empty
    if not folder_path and is_pod_empty(items):
        return render_template('welcome.html', pod_url=SOLID_POD_URL)

    items = sort_items(items, sort_by)
    breadcrumbs = build_breadcrumbs(folder_path)
    parts = [p for p in folder_path.split('/') if p]
    parent_path = '/'.join(parts[:-1]) if parts else None
    move_folders = get_move_folders(folder_path, items)
    file_count = sum(1 for i in items if not i['is_folder'])
    folder_count = sum(1 for i in items if i['is_folder'])
    recent_files = get_recent_files() if not folder_path else []
    share_link_url = request.args.get('share_link', '')
    stats = get_pod_stats_filesystem() if not folder_path else None
    return render_template('index.html',
        items=items,
        pod_url=SOLID_POD_URL,
        folder_path=folder_path,
        breadcrumbs=breadcrumbs,
        parent_path=parent_path,
        all_folders=get_all_folders(),
        move_folders=move_folders,
        file_count=file_count,
        folder_count=folder_count,
        recent_files=recent_files,
        default_folders=DEFAULT_FOLDERS,
        current_sort=sort_by,
        share_link_url=share_link_url,
        stats=stats,
    )


@app.route('/upload', methods=['POST'])
def upload():
    """Upload een bestand naar de gekozen map"""
    folder_path = request.form.get('upload_folder', '').strip('/')

    if 'file' not in request.files:
        flash('Geen bestand geselecteerd', 'error')
        return redirect_to_folder(folder_path)

    file = request.files['file']
    if file.filename == '':
        flash('Geen bestand geselecteerd', 'error')
        return redirect_to_folder(folder_path)

    if folder_path:
        relative_path = folder_path + '/' + file.filename
    else:
        relative_path = file.filename

    if pod_write(relative_path, file.read()):
        flash(f'"{file.filename}" succesvol geupload!', 'success')
        log_action('upload', {'file': file.filename, 'folder': folder_path or 'root'})
        auto_sync_after_change()
    else:
        flash('Upload mislukt: kon bestand niet opslaan', 'error')

    return redirect_to_folder(folder_path)


@app.route('/delete', methods=['POST'])
def delete():
    """Verplaats een resource naar de prullenbak"""
    resource_url = request.form.get('resource_url')
    folder_path = request.form.get('folder_path', '').strip('/')

    if not resource_url:
        flash('Geen resource opgegeven', 'error')
        return redirect_to_folder(folder_path)

    name = resource_url.rstrip('/').split('/')[-1]
    is_folder = resource_url.endswith('/')

    if is_folder:
        # Folders: direct verwijderen (niet naar prullenbak)
        rel_path = url_to_relative_path(resource_url)
        if rel_path and pod_delete(rel_path):
            flash(f'Map "{name}" verwijderd', 'success')
            log_action('delete', {'resource': name, 'folder': folder_path or 'root'})
            auto_sync_after_change()
        else:
            flash('Verwijderen mislukt', 'error')
        return redirect_to_folder(folder_path)

    # Files: verplaats naar prullenbak via filesystem
    # Step 1: Ensure _trash/ directory exists
    pod_mkdir('_trash')

    # Step 2: Read the file from filesystem
    rel_path = url_to_relative_path(resource_url)
    if not rel_path:
        flash('Verwijderen mislukt: ongeldig pad', 'error')
        return redirect_to_folder(folder_path)

    src_path = safe_pod_path(rel_path)
    if not src_path or not os.path.isfile(src_path):
        flash('Verwijderen mislukt: bestand niet gevonden', 'error')
        return redirect_to_folder(folder_path)

    # Step 3: Generate trash entry
    import uuid
    trash_id = uuid.uuid4().hex[:12]
    trash_filename = f'{trash_id}_{name}'
    trash_rel_path = '_trash/' + trash_filename
    trash_url = SOLID_POD_URL + trash_rel_path

    # Step 4: Copy to _trash/
    dst_path = safe_pod_path(trash_rel_path)
    if not dst_path:
        flash('Verplaatsen naar prullenbak mislukt', 'error')
        return redirect_to_folder(folder_path)

    shutil.copy2(src_path, dst_path)

    # Step 5: Delete original
    os.remove(src_path)

    # Step 6: Record in trash.json
    resource_path = folder_path + '/' + name if folder_path else name
    move_to_trash(resource_url, resource_path, name, folder_path or 'root', trash_url)

    flash(f'"{name}" naar prullenbak verplaatst', 'success')
    log_action('trash', {'resource': name, 'folder': folder_path or 'root'})
    auto_sync_after_change()
    return redirect_to_folder(folder_path)


@app.route('/create-folder', methods=['POST'])
def create_folder_route():
    """Maak een nieuwe submap aan in de huidige locatie"""
    folder_path = request.form.get('folder_path', '').strip('/')
    folder_name = request.form.get('folder_name', '')

    normalized = normalize_folder_name(folder_name)
    if not normalized:
        flash('Ongeldige mapnaam', 'error')
        return redirect_to_folder(folder_path)

    if folder_path:
        relative_path = folder_path + '/' + normalized
    else:
        relative_path = normalized

    if pod_exists(relative_path):
        flash(f'Map "{normalized}" bestaat al', 'error')
        return redirect_to_folder(folder_path)

    if pod_mkdir(relative_path):
        flash(f'Map "{normalized}" aangemaakt!', 'success')
        log_action('create_folder', {'name': normalized, 'path': folder_path or 'root'})
        auto_sync_after_change()
    else:
        flash('Map aanmaken mislukt', 'error')

    return redirect_to_folder(folder_path)


@app.route('/move', methods=['POST'])
def move():
    """Verplaats een bestand naar een andere map"""
    resource_url = request.form.get('resource_url', '')
    target_folder = request.form.get('target_folder', '').strip('/')
    folder_path = request.form.get('folder_path', '').strip('/')
    filename = resource_url.rstrip('/').split('/')[-1]

    if not resource_url or not filename:
        flash('Geen bestand opgegeven', 'error')
        return redirect_to_folder(folder_path)

    src_rel = url_to_relative_path(resource_url)
    if target_folder:
        dst_rel = target_folder + '/' + filename
    else:
        dst_rel = filename

    if src_rel == dst_rel:
        flash('Bestand staat al in deze map', 'error')
        return redirect_to_folder(folder_path)

    src_path = safe_pod_path(src_rel) if src_rel else None
    dst_path = safe_pod_path(dst_rel)

    if not src_path or not os.path.isfile(src_path):
        flash('Verplaatsen mislukt: bestand niet gevonden', 'error')
        return redirect_to_folder(folder_path)

    if not dst_path:
        flash('Verplaatsen mislukt: ongeldig doelpad', 'error')
        return redirect_to_folder(folder_path)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.move(src_path, dst_path)

    target_label = target_folder if target_folder else 'Pod root'
    flash(f'"{filename}" verplaatst naar {target_label}', 'success')
    log_action('move', {'file': filename, 'from': folder_path or 'root', 'to': target_folder or 'root'})
    auto_sync_after_change()
    return redirect_to_folder(folder_path)


# LEGACY: HTTP-gebaseerde zoekfunctie — bewaard voor toekomstige remote pod-toegang
def search_pod(container_url, query, path='', depth=0, max_depth=5):
    """Recursively search the pod for files matching the query"""
    if depth >= max_depth:
        return []

    results = []
    response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
    if not response or response.status_code != 200:
        return results

    items = parse_container_contents(response.text, container_url)
    for item in items:
        if item['is_folder']:
            sub_path = path + '/' + item['name'] if path else item['name']
            sub_url = item['url']
            results.extend(search_pod(sub_url, query, sub_path, depth + 1, max_depth))
        else:
            if query.lower() in item['name'].lower():
                file_path = path + '/' + item['name'] if path else item['name']
                results.append({
                    'name': item['name'],
                    'path': file_path,
                    'folder_path': path,
                    'url': item['url'],
                    'svg': item.get('svg'),
                })
    return results


@app.route('/search')
def search():
    """Search for files across all folders"""
    query = request.args.get('q', '').strip()
    results = []
    if query:
        results = search_pod_filesystem(query)
        log_action('search', {'query': query, 'results': len(results)})

    return render_template('search.html',
        query=query,
        results=results,
        pod_url=SOLID_POD_URL,
        all_folders=get_all_folders(),
    )


@app.route('/view/<path:file_path>')
def view_file(file_path):
    """View a file inline in the browser via filesystem"""
    full_path = safe_pod_path(file_path)
    if not full_path or not os.path.isfile(full_path):
        flash('Bestand kon niet worden geopend', 'error')
        return redirect(url_for('index'))

    filename = file_path.split('/')[-1]
    ext = os.path.splitext(filename)[1].lower()

    if ext in ('.mp3', '.wav', '.mp4', '.webm') and not request.args.get('raw'):
        folder_path = '/'.join(file_path.split('/')[:-1])
        return render_template('view.html',
            filename=filename,
            file_path=file_path,
            folder_path=folder_path,
            media_type='audio' if ext in ('.mp3', '.wav') else 'video',
            content_type=VIEWABLE_TYPES.get(ext, 'application/octet-stream'),
        )

    import mimetypes
    mime = VIEWABLE_TYPES.get(ext) or mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    if ext in VIEWABLE_TYPES:
        return send_file(full_path, mimetype=mime, download_name=filename)

    return send_file(full_path, as_attachment=True, download_name=filename)


@app.route('/download/<path:file_path>')
def download_file(file_path):
    """Force download a file from the pod via filesystem"""
    full_path = safe_pod_path(file_path)
    if not full_path or not os.path.isfile(full_path):
        flash('Bestand kon niet worden gedownload', 'error')
        return redirect(url_for('index'))

    filename = file_path.split('/')[-1]
    return send_file(full_path, as_attachment=True, download_name=filename)


def build_acl_content(resource_url):
    """Build ACL Turtle content from all active shares for this resource"""
    is_container = resource_url.endswith('/')
    shares = get_shares_for_resource(resource_url)

    acl = '@prefix acl: <http://www.w3.org/ns/auth/acl#>.\n'
    acl += '@prefix foaf: <http://xmlns.com/foaf/0.1/>.\n\n'
    acl += '<#owner>\n'
    acl += '    a acl:Authorization;\n'
    acl += f'    acl:agent <{OWNER_WEBID}>;\n'
    acl += f'    acl:accessTo <{resource_url}>;\n'
    if is_container:
        acl += f'    acl:default <{resource_url}>;\n'
    acl += '    acl:mode acl:Read, acl:Write, acl:Control.\n'

    for i, share in enumerate(shares, 1):
        acl += f'\n<#shared{i}>\n'
        acl += '    a acl:Authorization;\n'
        if share['webid'] == 'public':
            acl += '    acl:agentClass foaf:Agent;\n'
        else:
            acl += f'    acl:agent <{share["webid"]}>;\n'
        acl += f'    acl:accessTo <{resource_url}>;\n'
        if is_container:
            acl += f'    acl:default <{resource_url}>;\n'
        acl += f'    acl:mode {", ".join(share["modes"])}.\n'

    return acl


def write_acl(resource_url):
    """Write or delete ACL for a resource based on its active shares"""
    rel_path = url_to_relative_path(resource_url)
    if not rel_path:
        return

    acl_rel_path = rel_path + '.acl'
    shares = get_shares_for_resource(resource_url)

    if not shares:
        pod_delete(acl_rel_path)
        return

    acl_content = build_acl_content(resource_url)
    pod_write(acl_rel_path, acl_content)


@app.route('/share', methods=['POST'])
def share():
    """Share a resource with a WebID"""
    resource_url = request.form.get('resource_url', '')
    resource_path = request.form.get('resource_path', '')
    folder_path = request.form.get('folder_path', '').strip('/')
    webid = request.form.get('webid', '').strip()
    access_level = request.form.get('access_level', 'read')
    expires = request.form.get('expires', '').strip() or None

    if not resource_url:
        flash('Geen resource opgegeven', 'error')
        return redirect_to_folder(folder_path)

    if access_level == 'public':
        webid = 'public'
        modes = ['acl:Read']
    elif access_level == 'readwrite':
        modes = ['acl:Read', 'acl:Write']
    elif access_level == 'append':
        modes = ['acl:Append']
    else:
        modes = ['acl:Read']

    if not webid:
        flash('Vul een WebID in of kies openbaar', 'error')
        return redirect_to_folder(folder_path)

    add_share(resource_url, resource_path, webid, modes, expires)
    write_acl(resource_url)

    resource_name = resource_url.rstrip('/').split('/')[-1]
    display_webid = 'iedereen (openbaar)' if webid == 'public' else webid
    flash(f'"{resource_name}" gedeeld met {display_webid}', 'success')
    log_action('share', {'resource': resource_path, 'webid': webid, 'modes': modes})

    return redirect_to_folder(folder_path)


@app.route('/shares')
def shares_overview():
    """Show overview of all shared resources"""
    all_shares = get_all_shares()
    active_links = get_active_share_links()
    share_base_url = os.getenv('SHARE_BASE_URL', '').strip().rstrip('/')
    return render_template('shares.html', shares=all_shares, share_links=active_links, share_base_url=share_base_url)


@app.route('/share-link/create', methods=['POST'])
def create_share_link_route():
    """Genereer een deellink voor een bestand"""
    file_path = request.form.get('file_path', '')
    file_name = request.form.get('file_name', '')
    expires_days = int(request.form.get('expires_days', 7))
    password = request.form.get('password', '').strip() or None

    full_path = safe_pod_path(file_path)
    if not full_path or not os.path.isfile(full_path):
        flash('Bestand niet gevonden', 'error')
        return redirect(request.referrer or url_for('index'))

    link = create_share_link(file_path, file_name, expires_days, password)

    base_url = os.getenv('SHARE_BASE_URL', '').strip().rstrip('/')
    if base_url:
        share_url = f"{base_url}/share/{link['token']}"
    else:
        share_url = url_for('view_shared_file', token=link['token'], _external=True)

    log_action('share_link_created', {
        'file': file_name,
        'expires_days': expires_days,
        'has_password': password is not None
    })
    auto_sync_after_change()

    folder_path = '/'.join(file_path.split('/')[:-1])
    return redirect(url_for('browse', folder_path=folder_path) + '?share_link=' + share_url if folder_path else url_for('index') + '?share_link=' + share_url)


@app.route('/share/<token>', methods=['GET', 'POST'])
def view_shared_file(token):
    """Toon een gedeeld bestand via deellink"""
    link = get_share_link(token)

    if not link:
        return render_template('share_expired.html'), 404

    if link['password_hash']:
        if request.method == 'GET':
            return render_template('share_password.html', token=token)

        password = request.form.get('password', '')
        if hash_password(password) != link['password_hash']:
            flash('Onjuist wachtwoord', 'error')
            return render_template('share_password.html', token=token)

    full_path = safe_pod_path(link['file_path'])
    if not full_path or not os.path.isfile(full_path):
        return render_template('share_expired.html'), 404

    increment_download_count(token)

    import mimetypes
    content_type, _ = mimetypes.guess_type(link['file_name'])

    if content_type and (content_type.startswith('image/') or content_type == 'application/pdf'):
        return send_file(full_path, mimetype=content_type)
    else:
        return send_file(full_path, as_attachment=True, download_name=link['file_name'])


@app.route('/share-link/revoke', methods=['POST'])
def revoke_share_link():
    """Trek een deellink in"""
    link_id = request.form.get('link_id', '')
    if deactivate_share_link(link_id):
        flash('Deellink ingetrokken', 'success')
        log_action('share_link_revoked', {'link_id': link_id})
        auto_sync_after_change()
    else:
        flash('Deellink niet gevonden', 'error')
    return redirect(url_for('shares_overview'))


@app.route('/revoke', methods=['POST'])
def revoke():
    """Revoke access for a specific WebID to a resource"""
    resource_url = request.form.get('resource_url', '')
    webid = request.form.get('webid', '')
    resource_path = request.form.get('resource_path', '')

    if not resource_url or not webid:
        flash('Ongeldige verzoek', 'error')
        return redirect(url_for('shares_overview'))

    remove_share(resource_url, webid)
    write_acl(resource_url)

    resource_name = resource_url.rstrip('/').split('/')[-1]
    display_webid = 'iedereen (openbaar)' if webid == 'public' else webid
    flash(f'Toegang van {display_webid} tot "{resource_name}" ingetrokken', 'success')
    log_action('revoke', {'resource': resource_path, 'webid': webid})

    return redirect(url_for('shares_overview'))


@app.route('/audit')
def audit():
    """Show the audit log"""
    action_filter = request.args.get('filter', '')
    log = get_audit_log(action_filter if action_filter else None, limit=100)
    return render_template('audit.html', log=log, current_filter=action_filter)


# === TRASH ROUTES ===

@app.route('/trash')
def trash_overview():
    """Show trash contents"""
    # Auto-cleanup expired items
    expired = cleanup_expired()
    for item in expired:
        rel_path = url_to_relative_path(item['trash_url'])
        if rel_path:
            pod_delete(rel_path)
        add_notification('trash_auto_deleted', f'"{item["filename"]}" is definitief verwijderd uit prullenbak')
        log_action('trash_auto_deleted', {'file': item['filename']})

    trash_items = get_all_trash()
    return render_template('trash.html', trash_items=trash_items)


@app.route('/trash/restore', methods=['POST'])
def trash_restore():
    """Restore a file from trash to its original location"""
    trash_id = request.form.get('trash_id', '')

    entry = restore_from_trash(trash_id)
    if not entry:
        flash('Item niet gevonden in prullenbak', 'error')
        return redirect(url_for('trash_overview'))

    # Move from _trash/ back to original location via filesystem
    trash_rel = url_to_relative_path(entry['trash_url'])
    orig_rel = url_to_relative_path(entry['resource_url'])

    if not trash_rel or not orig_rel:
        flash('Herstellen mislukt: ongeldig pad', 'error')
        return redirect(url_for('trash_overview'))

    trash_path = safe_pod_path(trash_rel)
    orig_path = safe_pod_path(orig_rel)

    if not trash_path or not os.path.isfile(trash_path):
        flash('Herstellen mislukt: bestand niet gevonden in prullenbak', 'error')
        return redirect(url_for('trash_overview'))

    if not orig_path:
        flash('Herstellen mislukt: ongeldig doelpad', 'error')
        return redirect(url_for('trash_overview'))

    os.makedirs(os.path.dirname(orig_path), exist_ok=True)
    shutil.move(trash_path, orig_path)

    flash(f'"{entry["filename"]}" hersteld naar {entry.get("original_folder", "originele locatie")}', 'success')
    log_action('restore', {'file': entry['filename'], 'to': entry.get('original_folder', '')})
    return redirect(url_for('trash_overview'))


@app.route('/trash/delete', methods=['POST'])
def trash_permanent_delete():
    """Permanently delete a file from trash"""
    trash_id = request.form.get('trash_id', '')

    entry = permanent_delete(trash_id)
    if not entry:
        flash('Item niet gevonden in prullenbak', 'error')
        return redirect(url_for('trash_overview'))

    # Delete from pod _trash/ via filesystem
    rel_path = url_to_relative_path(entry['trash_url'])
    if rel_path:
        pod_delete(rel_path)

    flash(f'"{entry["filename"]}" definitief verwijderd', 'success')
    log_action('permanent_delete', {'file': entry['filename']})
    return redirect(url_for('trash_overview'))


# === NOTIFICATION ROUTES ===

@app.route('/notifications')
def notifications_page():
    """Show all notifications"""
    notifs = get_all_notifications()
    return render_template('notifications.html', notifications=notifs)


@app.route('/notifications/read', methods=['POST'])
def notification_mark_read():
    """Mark notification(s) as read"""
    notification_id = request.form.get('notification_id', '')
    if notification_id:
        mark_as_read(notification_id)
    else:
        mark_all_read()
    return redirect(url_for('notifications_page'))


# === PROFILE & SETTINGS ROUTES ===

# LEGACY: HTTP-gebaseerde statistieken — bewaard voor toekomstige remote pod-toegang
def get_storage_stats():
    """Calculate storage statistics by scanning the pod"""
    stats = {'file_count': 0, 'folder_count': 0, 'total_size': 0}

    def scan(container_url, depth=0, max_depth=5):
        if depth >= max_depth:
            return
        response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
        if not response or response.status_code != 200:
            return
        items = parse_container_contents(response.text, container_url)
        for item in items:
            if item['is_folder']:
                stats['folder_count'] += 1
                scan(item['url'], depth + 1, max_depth)
            else:
                stats['file_count'] += 1
                # Try to get file size
                head_resp = pod_request('GET', item['url'])
                if head_resp and head_resp.status_code == 200:
                    stats['total_size'] += len(head_resp.content)

    try:
        scan(SOLID_POD_URL)
    except Exception:
        pass
    return stats


def format_size(size_bytes):
    """Format bytes to human-readable size"""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    else:
        return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'


NL_MONTHS = ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']


def format_date_nl(http_date):
    """Format HTTP Last-Modified header to Dutch date like '15 mrt 2026'"""
    try:
        dt = parsedate_to_datetime(http_date)
        return f'{dt.day} {NL_MONTHS[dt.month - 1]} {dt.year}'
    except Exception:
        return '—'


@app.route('/profile')
def profile():
    """Show user profile with storage stats"""
    stats = get_pod_stats_filesystem()
    stats['total_size_formatted'] = format_size(stats['total_size'])
    bridge_password = os.getenv('BRIDGE_PASSWORD', '')
    bridge_url = os.getenv('SHARE_BASE_URL', '')
    return render_template('profile.html',
        webid=OWNER_WEBID,
        pod_url=SOLID_POD_URL,
        stats=stats,
        bridge_password=bridge_password,
        bridge_url=bridge_url,
        bridge_configured=bool(bridge_password),
    )


@app.route('/profile/bridge-password', methods=['POST'])
def change_bridge_password():
    if BRIDGE_MODE:
        abort(403)

    new_password = request.form.get('new_password', '').strip()

    if len(new_password) < 8:
        flash('Wachtwoord moet minimaal 8 tekens zijn', 'error')
        return redirect(url_for('profile'))

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

        found = False
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('BRIDGE_PASSWORD='):
                    f.write(f'BRIDGE_PASSWORD={new_password}\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f'BRIDGE_PASSWORD={new_password}\n')

        load_dotenv(env_path, override=True)
        os.environ['BRIDGE_PASSWORD'] = new_password

    flash('Bridge-wachtwoord gewijzigd', 'success')
    log_action('bridge_password_changed', {})
    return redirect(url_for('profile'))


@app.route('/settings')
def settings():
    """Show settings page"""
    return render_template('settings.html')


@app.route('/settings/export', methods=['POST'])
def export_backup():
    """Export entire pod as ZIP via filesystem"""
    pod_path = get_pod_data_path()
    buffer = io.BytesIO()

    try:
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(pod_path):
                # Skip verborgen mappen
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if f.startswith('.') or f.endswith('.acl') or f.endswith('.meta'):
                        continue
                    full_path = os.path.join(root, f)
                    arcname = os.path.relpath(full_path, pod_path).replace('\\', '/')
                    zf.write(full_path, arcname)
    except Exception as e:
        flash(f'Backup mislukt: {e}', 'error')
        return redirect(url_for('settings'))

    buffer.seek(0)
    log_action('export', {'type': 'zip_backup'})
    return Response(
        buffer.getvalue(),
        content_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename="mysolido-backup.zip"'}
    )


@app.route('/debug')
def debug():
    """Toon de raw Turtle response van de pod root"""
    try:
        response = pod_request('GET', SOLID_POD_URL, headers={'Accept': 'text/turtle'})
        if response and response.status_code == 200:
            return f'<pre>{response.text}</pre>'
        elif response:
            return f'<pre>Error {response.status_code}: {response.text}</pre>'
        else:
            return '<pre>Authenticatie mislukt</pre>'
    except requests.ConnectionError:
        return '<pre>CSS server niet bereikbaar</pre>'


@app.route('/init-folders')
def init_folders():
    """Maak de standaardmappen aan in de pod"""
    return _do_init_folders()


@app.route('/init-folders-welcome')
def init_folders_welcome():
    """Maak de standaardmappen aan vanuit het welkomstscherm"""
    return _do_init_folders(welcome=True)


def _do_init_folders(welcome=False):
    """Shared logic for creating default folders via filesystem"""
    created = []
    skipped = []

    for folder in DEFAULT_FOLDERS:
        if pod_exists(folder):
            skipped.append(folder)
            continue

        if pod_mkdir(folder):
            created.append(folder)
        else:
            flash(f'Map "{folder}" aanmaken mislukt', 'error')

    if welcome and created:
        flash('Je kluis is ingericht! Upload je eerste document.', 'success')
    else:
        if created:
            flash(f'{len(created)} mappen aangemaakt: {", ".join(created)}', 'success')
        if skipped:
            flash(f'{len(skipped)} mappen bestonden al: {", ".join(skipped)}', 'success')
        if not created and not skipped:
            flash('Geen mappen aangemaakt', 'error')

    return redirect(url_for('index'))


def redirect_to_folder(folder_path):
    """Redirect to the correct folder view"""
    if folder_path:
        return redirect(url_for('browse', folder_path=folder_path))
    return redirect(url_for('index'))


if __name__ == '__main__':
    print()

    if BRIDGE_MODE:
        bridge_pw = os.getenv('BRIDGE_PASSWORD', os.getenv('CSS_PASSWORD', ''))
        print("  === MySolido Bridge ===")
        print("  [BRIDGE] Read-only modus")
        print(f"  Pod: {SOLID_POD_URL}")
        if bridge_pw:
            print(f"  Wachtwoord: {bridge_pw}")
        else:
            print("  [WAARSCHUWING] Geen BRIDGE_PASSWORD of CSS_PASSWORD ingesteld!")
        print(f"  Start op http://127.0.0.1:5000")
        print("  ========================")
        print()
        app.run(port=5000, debug=True)
    else:
        print("  === MySolido ===")

        if not auto_setup():
            print()
            print("  Setup mislukt. Zorg dat Community Solid Server draait op poort 3000:")
            print("  npx @solid/community-server -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json")
            print()
            exit(1)

        print()
        print(f"  Pod: {os.getenv('SOLID_POD_URL')}")
        print(f"  Start op http://localhost:5000")
        print("  ================")
        print()

        app.run(port=5000, debug=True)
