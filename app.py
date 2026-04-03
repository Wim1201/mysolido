import re
import os
import io
import sys
import time
import uuid
import secrets
import string
import zipfile
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import unquote
from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file, session, abort
import requests
import base64
import bcrypt
from dotenv import load_dotenv
from audit import log_action, get_audit_log
from shares import add_share, remove_share, get_all_shares, get_shares_for_resource, check_expired_shares
from trash import move_to_trash, restore_from_trash, permanent_delete, get_all_trash, cleanup_expired
from notifications import add_notification, get_all_notifications, get_unread_count, mark_as_read, mark_all_read
from share_links import (
    create_share_link, get_share_link, deactivate_share_link,
    get_active_share_links, increment_download_count,
    check_password as check_share_password
)
from sync_bridge import (
    is_configured as bridge_sync_configured,
    get_status as get_bridge_sync_status,
    sync_in_background,
    auto_sync_after_change
)
from watermark import watermark_pdf, watermark_image, get_watermark_text
import tempfile as _tempfile

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
TEMP_DIR = os.path.join(PROJECT_DIR, 'temp')

# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)


def is_watermark_enabled():
    """Check if watermarking is enabled (default: True)"""
    return os.getenv('WATERMARK_ENABLED', 'true').lower() in ('true', '1', 'yes')


def cleanup_temp_files(max_age_seconds=3600):
    """Remove temp files older than max_age_seconds"""
    now = time.time()
    if os.path.isdir(TEMP_DIR):
        for fname in os.listdir(TEMP_DIR):
            fpath = os.path.join(TEMP_DIR, fname)
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > max_age_seconds:
                try:
                    os.remove(fpath)
                except OSError:
                    pass


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


def hash_password_bcrypt(password):
    """Hash een wachtwoord met bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password_bcrypt(password, hashed):
    """Controleer een wachtwoord tegen een bcrypt hash"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, AttributeError):
        # Fallback voor migratie-periode: directe vergelijking met plain text
        return password == hashed


def is_bcrypt_hash(value):
    """Check of een waarde een bcrypt hash is"""
    return value and (value.startswith('$2b$') or value.startswith('$2a$'))


def migrate_passwords_to_bcrypt():
    """Migreer plain text wachtwoorden naar bcrypt hashes in .env"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return

    changed = False
    lines = []

    with open(env_path, 'r') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()

        if stripped.startswith('BRIDGE_PASSWORD='):
            value = stripped.split('=', 1)[1]
            if value and not is_bcrypt_hash(value):
                hashed = hash_password_bcrypt(value)
                new_lines.append(f'BRIDGE_PASSWORD={hashed}\n')
                os.environ['BRIDGE_PASSWORD'] = hashed
                changed = True
                print("  [OK] BRIDGE_PASSWORD gehasht met bcrypt")
                continue

        if stripped.startswith('CSS_PASSWORD='):
            value = stripped.split('=', 1)[1]
            if value and not is_bcrypt_hash(value):
                hashed = hash_password_bcrypt(value)
                new_lines.append(f'CSS_PASSWORD={hashed}\n')
                os.environ['CSS_PASSWORD'] = hashed
                changed = True
                print("  [OK] CSS_PASSWORD gehasht met bcrypt")
                continue

        new_lines.append(line)

    if changed:
        with open(env_path, 'w') as f:
            f.writelines(new_lines)
        print("  [OK] Wachtwoorden gemigreerd naar bcrypt")


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
                    timeout=15)
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
        bridge_pw_plain = generate_password()
        bridge_pw_hash = hash_password_bcrypt(bridge_pw_plain)

        with open(env_path, 'w') as f:
            f.write(f'CSS_BASE_URL={css_base}\n')
            f.write(f'SOLID_POD_URL={pod_url}\n')
            f.write(f'WEBID={webid}\n')
            f.write(f'CSS_EMAIL={email}\n')
            f.write(f'CSS_PASSWORD={password}\n')
            f.write(f'CLIENT_ID={client_id}\n')
            f.write(f'CLIENT_SECRET={client_secret}\n')
            f.write('SHARE_BASE_URL=http://localhost:5000\n')
            f.write(f'BRIDGE_PASSWORD={bridge_pw_hash}\n')
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
        print(f"  [OK] Bridge wachtwoord: {bridge_pw_plain}")
        print(f"       (Bewaar dit wachtwoord! Het wordt gehasht opgeslagen)")

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
    'werk', 'voertuigen', 'juridisch', 'media', 'accounts',
    'gezin', 'abonnementen', 'inbox', 'verzekeringen',
    'huisdieren', 'opleiding', 'reizen', 'digitaal-testament',
    'persoonlijk', 'projecten', 'toestemmingen',
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
    'accounts': {
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
    'toestemmingen': {
        'color': '#2e8b57',
        'svg': '<svg viewBox="0 0 24 24" fill="none" stroke="#2e8b57" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>'
    },
}


@app.before_request
def check_bridge_auth():
    if not BRIDGE_MODE:
        return

    public_routes = [
        'bridge_login', 'view_shared_file', 'static',
        'verzoek_formulier', 'verzoek_submit', 'verzoek_status', 'verzoek_response',
    ]

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
        'consent_list': 'toestemmingen',
        'consent_new': 'toestemmingen',
        'consent_detail': 'toestemmingen',
        'consent_withdraw': 'toestemmingen',
        'consent_delete': 'toestemmingen',
        'edit_policy': 'kluis',
        'intenties_overview': 'profiel',
        'intentie_new': 'profiel',
        'intentie_detail': 'profiel',
        'intentie_activate': 'profiel',
        'intentie_withdraw': 'profiel',
        'intentie_delete': 'profiel',
        'verzoeken_overview': 'profiel',
        'verzoek_detail_owner': 'profiel',
        'verzoek_approve': 'profiel',
        'verzoek_reject': 'profiel',
    }
    active = nav_map.get(request.endpoint, '')
    return {
        'folder_icons': FOLDER_ICONS,
        'unread_count': get_unread_count(),
        'new_requests_count': count_new_requests(),
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

        if check_password_bcrypt(password, bridge_password):
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
    consent_stats = get_consent_stats() if not folder_path else None

    # Get policy info for current folder
    folder_policy = None
    folder_policy_summary = None
    if folder_path:
        fp = safe_pod_path(folder_path)
        if fp and os.path.isdir(fp):
            folder_policy = get_container_policy(fp)
            folder_policy_summary = policy_summary_nl(folder_policy)

    # Build policy summaries for folder grid on dashboard
    folder_policies = {}
    if not folder_path:
        pod_path = get_pod_data_path()
        for fname in DEFAULT_FOLDERS:
            fdir = os.path.join(pod_path, fname)
            if os.path.isdir(fdir):
                p = get_container_policy(fdir)
                folder_policies[fname] = policy_summary_nl(p)

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
        consent_stats=consent_stats,
        folder_policy=folder_policy,
        folder_policy_summary=folder_policy_summary,
        folder_policies=folder_policies,
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
        if not check_share_password(password, link['password_hash']):
            flash('Onjuist wachtwoord', 'error')
            return render_template('share_password.html', token=token)

    full_path = safe_pod_path(link['file_path'])
    if not full_path or not os.path.isfile(full_path):
        return render_template('share_expired.html'), 404

    increment_download_count(token)

    import mimetypes
    content_type, _ = mimetypes.guess_type(link['file_name'])

    # Apply watermark for PDFs and images if enabled
    if is_watermark_enabled() and content_type:
        ext = os.path.splitext(link['file_name'])[1].lower()
        wm_text = get_watermark_text()
        temp_path = os.path.join(TEMP_DIR, f"wm_{token}_{link['file_name']}")

        if content_type == 'application/pdf':
            if watermark_pdf(full_path, temp_path, wm_text):
                response = send_file(temp_path, mimetype=content_type)
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                return response

        elif content_type.startswith('image/') and ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
            if watermark_image(full_path, temp_path, wm_text):
                response = send_file(temp_path, mimetype=content_type)
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                return response

    # Fallback: serve original without watermark
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

    hashed = hash_password_bcrypt(new_password)

    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

        found = False
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('BRIDGE_PASSWORD='):
                    f.write(f'BRIDGE_PASSWORD={hashed}\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f'BRIDGE_PASSWORD={hashed}\n')

        load_dotenv(env_path, override=True)
        os.environ['BRIDGE_PASSWORD'] = hashed

    flash('Bridge-wachtwoord gewijzigd', 'success')
    log_action('bridge_password_changed', {})
    return redirect(url_for('profile'))


@app.route('/settings')
def settings():
    """Show settings page"""
    return render_template('settings.html', watermark_enabled=is_watermark_enabled())


@app.route('/settings/watermark', methods=['POST'])
def toggle_watermark():
    """Toggle watermark setting in .env"""
    if BRIDGE_MODE:
        flash('Niet beschikbaar in Bridge-modus', 'error')
        return redirect(url_for('settings'))

    enabled = 'true' if request.form.get('enabled') == 'true' else 'false'
    env_path = os.path.join(PROJECT_DIR, '.env')

    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

        found = False
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('WATERMARK_ENABLED='):
                    f.write(f'WATERMARK_ENABLED={enabled}\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f'WATERMARK_ENABLED={enabled}\n')
    else:
        with open(env_path, 'w') as f:
            f.write(f'WATERMARK_ENABLED={enabled}\n')

    # Reload env so the change takes effect immediately
    os.environ['WATERMARK_ENABLED'] = enabled

    status = 'ingeschakeld' if enabled == 'true' else 'uitgeschakeld'
    flash(f'Watermerken {status}', 'success')
    return redirect(url_for('settings'))


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


# === ODRL POLICY FUNCTIONS ===

import json as _json


def get_container_policy(container_path):
    """Read the ODRL policy for a container, return dict or None"""
    policy_file = os.path.join(container_path, '.policy.jsonld')
    if os.path.exists(policy_file):
        with open(policy_file, 'r', encoding='utf-8') as f:
            return _json.load(f)
    return None


def policy_summary_nl(policy):
    """Generate a Dutch summary of an ODRL policy"""
    if policy is None:
        return "Geen policy ingesteld"

    permissions = policy.get('permission', [])
    prohibitions = policy.get('prohibition', [])

    parts = []
    has_owner_only = False
    has_anyone_read = False
    has_distribute_prohibition = False
    has_temporal = False

    for perm in permissions:
        assignee = perm.get('assignee', 'onbekend')
        actions = perm.get('action', [])
        if isinstance(actions, str):
            actions = [actions]
        if assignee == 'urn:mysolido:owner':
            has_owner_only = True
        elif assignee == 'urn:mysolido:anyone':
            has_anyone_read = 'read' in actions
            if perm.get('constraint'):
                has_temporal = True

    for prohib in prohibitions:
        actions = prohib.get('action', [])
        if isinstance(actions, str):
            actions = [actions]
        if 'distribute' in actions:
            has_distribute_prohibition = True

    if has_temporal and has_anyone_read:
        return "Tijdelijk delen"
    elif has_anyone_read and has_distribute_prohibition:
        return "Lezen, niet downloaden"
    elif has_anyone_read:
        return "Lezen toegestaan"
    elif has_owner_only and has_distribute_prohibition:
        return "Alleen eigenaar \u2014 niet delen"
    elif has_owner_only:
        return "Alleen eigenaar"
    else:
        return "Aangepaste policy"


def build_policy(folder_name, rule):
    """Build an ODRL policy dict for a given rule type"""
    policy = {
        "@context": [
            "http://www.w3.org/ns/odrl.jsonld",
            {"dpv": "https://w3id.org/dpv#"}
        ],
        "@type": "Set",
        "uid": f"urn:mysolido:policy:{folder_name}",
        "profile": "http://www.w3.org/ns/odrl/2/core",
        "permission": [
            {
                "target": f"urn:mysolido:container:{folder_name}",
                "assignee": "urn:mysolido:owner",
                "action": ["read", "write", "delete"]
            }
        ],
        "prohibition": [
            {
                "target": f"urn:mysolido:container:{folder_name}",
                "action": "distribute"
            }
        ]
    }

    if rule == 'read':
        policy['permission'].append({
            "target": f"urn:mysolido:container:{folder_name}",
            "assignee": "urn:mysolido:anyone",
            "action": "read"
        })
        policy['prohibition'] = []
    elif rule == 'read-no-download':
        policy['permission'].append({
            "target": f"urn:mysolido:container:{folder_name}",
            "assignee": "urn:mysolido:anyone",
            "action": "read"
        })
    elif rule == 'temporal':
        policy['permission'].append({
            "target": f"urn:mysolido:container:{folder_name}",
            "assignee": "urn:mysolido:anyone",
            "action": "read",
            "constraint": {
                "leftOperand": "dateTime",
                "operator": "lteq",
                "rightOperand": {
                    "@type": "xsd:dateTime",
                    "@value": (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
                }
            }
        })
    # rule == 'owner' uses the default (owner only, no distribute)

    return policy


def detect_policy_rule(policy):
    """Detect which rule type a policy represents"""
    if policy is None:
        return 'owner'

    permissions = policy.get('permission', [])
    prohibitions = policy.get('prohibition', [])

    has_anyone_read = False
    has_temporal = False
    has_distribute_prohibition = False

    for perm in permissions:
        if perm.get('assignee') == 'urn:mysolido:anyone' and 'read' in (perm.get('action') if isinstance(perm.get('action'), list) else [perm.get('action', '')]):
            has_anyone_read = True
            if perm.get('constraint'):
                has_temporal = True

    for prohib in prohibitions:
        actions = prohib.get('action', [])
        if isinstance(actions, str):
            actions = [actions]
        if 'distribute' in actions:
            has_distribute_prohibition = True

    if has_temporal:
        return 'temporal'
    elif has_anyone_read and has_distribute_prohibition:
        return 'read-no-download'
    elif has_anyone_read:
        return 'read'
    return 'owner'


def init_default_policies():
    """Create default .policy.jsonld for each standard folder if not present"""
    pod_path = get_pod_data_path()
    for folder in DEFAULT_FOLDERS:
        folder_path = os.path.join(pod_path, folder)
        if not os.path.isdir(folder_path):
            continue
        policy_file = os.path.join(folder_path, '.policy.jsonld')
        if not os.path.exists(policy_file):
            policy = build_policy(folder, 'owner')
            with open(policy_file, 'w', encoding='utf-8') as f:
                _json.dump(policy, f, indent=4, ensure_ascii=False)


@app.route('/policy/<path:folder_path>', methods=['GET', 'POST'])
def edit_policy(folder_path):
    """View and edit the ODRL policy for a container"""
    if BRIDGE_MODE:
        flash('Niet beschikbaar in Bridge-modus', 'error')
        return redirect(url_for('index'))

    folder_path = folder_path.strip('/')
    full_path = safe_pod_path(folder_path)
    if not full_path or not os.path.isdir(full_path):
        flash('Map niet gevonden', 'error')
        return redirect(url_for('index'))

    folder_name = folder_path.split('/')[-1] if '/' in folder_path else folder_path

    if request.method == 'POST':
        rule = request.form.get('rule', 'owner')
        policy = build_policy(folder_name, rule)
        policy_file = os.path.join(full_path, '.policy.jsonld')
        with open(policy_file, 'w', encoding='utf-8') as f:
            _json.dump(policy, f, indent=4, ensure_ascii=False)
        flash(f'Policy bijgewerkt voor {folder_name}', 'success')
        log_action('policy_update', {'folder': folder_path, 'rule': rule})
        return redirect(url_for('edit_policy', folder_path=folder_path))

    policy = get_container_policy(full_path)
    current_rule = detect_policy_rule(policy)
    summary = policy_summary_nl(policy)
    breadcrumbs = build_breadcrumbs(folder_path)

    return render_template('policy_edit.html',
        folder_path=folder_path,
        folder_name=folder_name,
        policy=policy,
        current_rule=current_rule,
        summary=summary,
        breadcrumbs=breadcrumbs,
    )


# === CONSENT MODULE ===

PURPOSE_MAP = {
    'medical': {'@type': 'dpv:ServiceProvision', 'label': 'Medische behandeling'},
    'legal': {'@type': 'dpv:LegalCompliance', 'label': 'Juridisch advies'},
    'financial': {'@type': 'dpv:ServiceProvision', 'label': 'Financieel advies'},
    'insurance': {'@type': 'dpv:ServiceProvision', 'label': 'Verzekering'},
    'government': {'@type': 'dpv:LegalObligation', 'label': 'Overheid'},
    'education': {'@type': 'dpv:ServiceProvision', 'label': 'Onderwijs'},
    'other': {'@type': 'dpv:Purpose', 'label': 'Overig'},
}

DATA_CATEGORY_MAP = {
    'identity': {'@type': 'dpv:Identifying', 'label': 'Identiteitsgegevens'},
    'medical': {'@type': 'dpv:MedicalHealth', 'label': 'Medische gegevens'},
    'financial': {'@type': 'dpv:Financial', 'label': 'Financi\u00eble gegevens'},
    'legal': {'@type': 'dpv:Official', 'label': 'Juridische documenten'},
    'work': {'@type': 'dpv:Professional', 'label': 'Werkgerelateerd'},
    'other': {'@type': 'dpv:PersonalData', 'label': 'Overig'},
}


def get_consent_dir():
    """Return the absolute path to the toestemmingen folder"""
    return safe_pod_path('toestemmingen')


def load_all_consents():
    """Load all consent records from the toestemmingen folder"""
    consent_dir = get_consent_dir()
    if not consent_dir or not os.path.isdir(consent_dir):
        return []

    consents = []
    for fname in os.listdir(consent_dir):
        if fname.endswith('.jsonld') and not fname.startswith('.'):
            fpath = os.path.join(consent_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    record = _json.load(f)
                record['_filename'] = fname
                record['_id'] = fname.replace('.jsonld', '')
                consents.append(record)
            except (_json.JSONDecodeError, IOError):
                continue

    consents.sort(key=lambda r: r.get('dct:created', ''), reverse=True)
    return consents


def get_consent_status_display(record):
    """Return status display info for a consent record"""
    status = record.get('dpv:hasConsentStatus', '')
    if status == 'dpv:ConsentStatusWithdrawn':
        return {'label': 'Ingetrokken', 'icon': '\u274c', 'class': 'status-withdrawn'}

    expiry = record.get('dpv:hasExpiry', {})
    expiry_time = expiry.get('dpv:hasExpiryTime', '') if isinstance(expiry, dict) else ''
    if expiry_time:
        try:
            exp_dt = datetime.fromisoformat(expiry_time.replace('Z', '+00:00'))
            if exp_dt < datetime.now(exp_dt.tzinfo):
                return {'label': 'Verlopen', 'icon': '\u23f0', 'class': 'status-expired'}
        except (ValueError, TypeError):
            pass

    if status == 'dpv:ConsentStatusGiven':
        return {'label': 'Actief', 'icon': '\u2705', 'class': 'status-active'}

    return {'label': 'Onbekend', 'icon': '\u2753', 'class': 'status-unknown'}


def get_consent_stats():
    """Return consent statistics for the dashboard"""
    consents = load_all_consents()
    active = 0
    expired = 0
    withdrawn = 0
    for c in consents:
        status = get_consent_status_display(c)
        if status['class'] == 'status-active':
            active += 1
        elif status['class'] == 'status-expired':
            expired += 1
        elif status['class'] == 'status-withdrawn':
            withdrawn += 1
    return {'active': active, 'expired': expired, 'withdrawn': withdrawn, 'total': len(consents)}


def generate_consent_id():
    """Generate a unique consent ID: urn:mysolido:consent:YYYYMMDD-NNN"""
    consent_dir = get_consent_dir()
    date_str = datetime.utcnow().strftime('%Y%m%d')
    existing = []
    if consent_dir and os.path.isdir(consent_dir):
        for fname in os.listdir(consent_dir):
            if fname.startswith(date_str) and fname.endswith('.jsonld'):
                try:
                    num = int(fname.replace('.jsonld', '').split('-')[-1])
                    existing.append(num)
                except (ValueError, IndexError):
                    pass
    next_num = max(existing, default=0) + 1
    return f"{date_str}-{next_num:03d}"


@app.route('/consent')
def consent_list():
    """Overview of all consent records"""
    consents = load_all_consents()
    enriched = []
    for c in consents:
        c['_status'] = get_consent_status_display(c)
        # Extract readable fields
        controller = c.get('dpv:hasDataController', {})
        c['_receiver'] = controller.get('dct:title', 'Onbekend') if isinstance(controller, dict) else str(controller)
        purpose = c.get('dpv:hasPurpose', {})
        c['_purpose'] = purpose.get('dct:description', purpose.get('@type', 'Onbekend')) if isinstance(purpose, dict) else str(purpose)
        expiry = c.get('dpv:hasExpiry', {})
        c['_expiry_date'] = expiry.get('dpv:hasExpiryTime', '')[:10] if isinstance(expiry, dict) else ''
        enriched.append(c)

    return render_template('consent_list.html', consents=enriched)


@app.route('/consent/new', methods=['GET', 'POST'])
def consent_new():
    """Create a new consent record"""
    if BRIDGE_MODE:
        flash('Niet beschikbaar in Bridge-modus', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        receiver = request.form.get('receiver', '').strip()
        purpose_key = request.form.get('purpose', 'other')
        category_key = request.form.get('category', 'other')
        expires = request.form.get('expires', '').strip()
        note = request.form.get('note', '').strip()

        if not title or not receiver:
            flash('Titel en ontvanger zijn verplicht', 'error')
            return redirect(url_for('consent_new'))

        consent_id = generate_consent_id()
        now = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        purpose_info = PURPOSE_MAP.get(purpose_key, PURPOSE_MAP['other'])
        category_info = DATA_CATEGORY_MAP.get(category_key, DATA_CATEGORY_MAP['other'])

        record = {
            "@context": [
                "http://www.w3.org/ns/odrl.jsonld",
                {
                    "dpv": "https://w3id.org/dpv#",
                    "dct": "http://purl.org/dc/terms/",
                    "xsd": "http://www.w3.org/2001/XMLSchema#"
                }
            ],
            "@type": "dpv:ConsentRecord",
            "@id": f"urn:mysolido:consent:{consent_id}",
            "dct:title": title,
            "dct:created": now,
            "dct:modified": now,
            "dpv:hasDataSubject": "urn:mysolido:owner",
            "dpv:hasDataController": {
                "@id": f"urn:mysolido:party:{secrets.token_hex(4)}",
                "dct:title": receiver
            },
            "dpv:hasPurpose": {
                "@type": purpose_info['@type'],
                "dct:description": purpose_info['label']
            },
            "dpv:hasPersonalDataCategory": category_info['@type'],
            "dpv:hasConsentStatus": "dpv:ConsentStatusGiven",
            "dpv:hasLegalBasis": "dpv:Consent",
            "dpv:hasRight": "dpv:RightToWithdrawConsent"
        }

        if description:
            record["dct:description"] = description
        if note:
            record["dpv:note"] = note
        if expires:
            record["dpv:hasExpiry"] = {
                "@type": "dpv:TemporalDuration",
                "dpv:hasExpiryTime": f"{expires}T00:00:00Z"
            }

        consent_dir = get_consent_dir()
        if consent_dir:
            os.makedirs(consent_dir, exist_ok=True)
            fpath = os.path.join(consent_dir, f"{consent_id}.jsonld")
            with open(fpath, 'w', encoding='utf-8') as f:
                _json.dump(record, f, indent=4, ensure_ascii=False)
            flash(f'Toestemming "{title}" vastgelegd', 'success')
            log_action('consent_create', {'title': title, 'receiver': receiver})
        else:
            flash('Toestemmingen-map niet gevonden', 'error')

        return redirect(url_for('consent_list'))

    return render_template('consent_form.html',
        purposes=PURPOSE_MAP,
        categories=DATA_CATEGORY_MAP,
    )


@app.route('/consent/<consent_id>')
def consent_detail(consent_id):
    """View a single consent record"""
    consent_dir = get_consent_dir()
    if not consent_dir:
        flash('Toestemmingen-map niet gevonden', 'error')
        return redirect(url_for('consent_list'))

    fpath = os.path.join(consent_dir, f"{consent_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Toestemming niet gevonden', 'error')
        return redirect(url_for('consent_list'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['_id'] = consent_id
    record['_status'] = get_consent_status_display(record)

    return render_template('consent_detail.html', consent=record)


@app.route('/consent/<consent_id>/withdraw', methods=['POST'])
def consent_withdraw(consent_id):
    """Withdraw a consent record"""
    if BRIDGE_MODE:
        flash('Niet beschikbaar in Bridge-modus', 'error')
        return redirect(url_for('consent_list'))

    consent_dir = get_consent_dir()
    if not consent_dir:
        flash('Toestemmingen-map niet gevonden', 'error')
        return redirect(url_for('consent_list'))

    fpath = os.path.join(consent_dir, f"{consent_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Toestemming niet gevonden', 'error')
        return redirect(url_for('consent_list'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['dpv:hasConsentStatus'] = 'dpv:ConsentStatusWithdrawn'
    record['dct:modified'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=4, ensure_ascii=False)

    title = record.get('dct:title', consent_id)
    flash(f'Toestemming "{title}" ingetrokken', 'success')
    log_action('consent_withdraw', {'id': consent_id, 'title': title})
    return redirect(url_for('consent_list'))


@app.route('/consent/<consent_id>/delete', methods=['POST'])
def consent_delete(consent_id):
    """Delete a consent record"""
    if BRIDGE_MODE:
        flash('Niet beschikbaar in Bridge-modus', 'error')
        return redirect(url_for('consent_list'))

    consent_dir = get_consent_dir()
    if not consent_dir:
        flash('Toestemmingen-map niet gevonden', 'error')
        return redirect(url_for('consent_list'))

    fpath = os.path.join(consent_dir, f"{consent_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Toestemming niet gevonden', 'error')
        return redirect(url_for('consent_list'))

    os.remove(fpath)
    flash('Toestemming verwijderd', 'success')
    log_action('consent_delete', {'id': consent_id})
    return redirect(url_for('consent_list'))


# === PROFILE DATA MODULE (Omgekeerde Google) ===


@app.route('/profiel-data', methods=['GET'])
def profiel_data():
    """Show profile data form (Omgekeerde Google)"""
    data = {}
    profile_path = safe_pod_path('profiel/profiel.jsonld')
    if profile_path and os.path.exists(profile_path):
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = _json.load(f)
        except (ValueError, IOError):
            data = {}

    return render_template('profiel_data.html',
        data=data,
        read_only=BRIDGE_MODE,
    )


@app.route('/profiel-data', methods=['POST'])
def profiel_data_save():
    """Save profile data as JSON-LD"""
    if BRIDGE_MODE:
        abort(403)

    form = request.form

    # Build JSON-LD document
    profile = {
        "@context": {
            "dpv": "https://w3id.org/dpv#",
            "pd": "https://w3id.org/dpv/pd#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "mysolido": "https://mysolido.com/vocab#"
        },
        "@type": "dpv:PersonalData"
    }

    # Housing
    if form.get('housing_type'):
        profile['pd:HousingOwnership'] = form['housing_type']
    if form.get('housing_kind'):
        profile['mysolido:housingType'] = form['housing_kind']
    if form.get('region'):
        profile['pd:Location'] = form['region']

    # Family
    if form.get('household_size'):
        try:
            profile['pd:HouseholdSize'] = int(form['household_size'])
        except ValueError:
            pass
    child_ages = form.getlist('child_age[]')
    if child_ages:
        children = [{"ageCategory": a} for a in child_ages if a]
        if children:
            profile['pd:FamilyStructure'] = {"children": children}

    # Vehicles
    v_type = form.get('vehicle_type')
    if v_type:
        vehicle = {"type": v_type}
        if form.get('vehicle_fuel'):
            vehicle['fuel'] = form['vehicle_fuel']
        if form.get('vehicle_year'):
            try:
                vehicle['yearBuilt'] = int(form['vehicle_year'])
            except ValueError:
                pass
        profile['pd:Vehicle'] = [vehicle]

    # Insurance (multiple)
    ins_types = form.getlist('ins_type[]')
    ins_providers = form.getlist('ins_provider[]')
    ins_dates = form.getlist('ins_enddate[]')
    insurances = []
    for i in range(len(ins_types)):
        if ins_types[i]:
            ins = {"type": ins_types[i]}
            if i < len(ins_providers) and ins_providers[i]:
                ins['provider'] = ins_providers[i]
            if i < len(ins_dates) and ins_dates[i]:
                ins['endDate'] = ins_dates[i]
            insurances.append(ins)
    if insurances:
        profile['pd:Insurance'] = insurances

    # Work
    if form.get('work_sector') or form.get('employment_type'):
        occupation = {}
        if form.get('work_sector'):
            occupation['sector'] = form['work_sector']
        if form.get('employment_type'):
            occupation['employmentType'] = form['employment_type']
        profile['pd:Occupation'] = occupation

    # Health
    if form.get('smoking') or form.get('gp_practice'):
        health = {}
        if form.get('smoking'):
            health['smokingStatus'] = form['smoking']
        if form.get('gp_practice'):
            health['gpPractice'] = form['gp_practice']
        profile['pd:HealthData'] = health

    # Ensure profiel directory exists
    pod_mkdir('profiel')

    # Write profile JSON-LD
    pod_write('profiel/profiel.jsonld',
              _json.dumps(profile, indent=2, ensure_ascii=False))

    # Create ODRL policy if it doesn't exist yet
    if not pod_exists('profiel/.policy.jsonld'):
        policy = {
            "@context": [
                "http://www.w3.org/ns/odrl.jsonld",
                {"dpv": "https://w3id.org/dpv#"}
            ],
            "@type": "Set",
            "uid": "urn:mysolido:policy:profiel",
            "profile": "http://www.w3.org/ns/odrl/2/core",
            "permission": [{
                "target": "urn:mysolido:container:profiel",
                "assignee": "urn:mysolido:owner",
                "action": ["read", "write", "delete"]
            }],
            "prohibition": [{
                "target": "urn:mysolido:container:profiel",
                "action": "distribute"
            }]
        }
        pod_write('profiel/.policy.jsonld',
                  _json.dumps(policy, indent=2, ensure_ascii=False))

    flash('Profielgegevens opgeslagen', 'success')
    return redirect(url_for('profiel_data'))


# === INTENTION MODULE (Omgekeerde Google — Fase 2) ===

INTENTION_CATEGORIES = {
    'autoverzekering': {'label': 'Autoverzekering', 'icon': '\U0001f697', 'profile_fields': ['vehicle', 'insurance']},
    'zorgverzekering': {'label': 'Zorgverzekering', 'icon': '\U0001f3e5', 'profile_fields': ['health', 'household']},
    'woonverzekering': {'label': 'Woonverzekering', 'icon': '\U0001f3e0', 'profile_fields': ['housing', 'insurance']},
    'energiecontract': {'label': 'Energiecontract', 'icon': '\u26a1', 'profile_fields': ['housing', 'household']},
    'hypotheek': {'label': 'Hypotheek', 'icon': '\U0001f3e6', 'profile_fields': ['housing', 'occupation', 'household']},
    'reisverzekering': {'label': 'Reisverzekering', 'icon': '\u2708\ufe0f', 'profile_fields': ['household', 'insurance']},
    'rechtsbijstand': {'label': 'Rechtsbijstand', 'icon': '\u2696\ufe0f', 'profile_fields': ['occupation', 'household']},
    'pensioen': {'label': 'Pensioen', 'icon': '\U0001f9d3', 'profile_fields': ['occupation', 'household']},
    'internet_tv': {'label': 'Internet & TV', 'icon': '\U0001f4e1', 'profile_fields': ['housing', 'household']},
    'anders': {'label': 'Anders', 'icon': '\U0001f4cb', 'profile_fields': []},
}

VALIDITY_OPTIONS = {
    '1w': {'label': '1 week', 'days': 7},
    '2w': {'label': '2 weken', 'days': 14},
    '1m': {'label': '1 maand', 'days': 30},
    '3m': {'label': '3 maanden', 'days': 90},
}


def get_intenties_dir():
    """Return the absolute path to the intenties folder"""
    return safe_pod_path('intenties')


def load_profile_data():
    """Load the profile data from profiel.jsonld"""
    profile_path = safe_pod_path('profiel/profiel.jsonld')
    if profile_path and os.path.exists(profile_path):
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                return _json.load(f)
        except (ValueError, IOError):
            pass
    return {}


def extract_profile_groups(profile):
    """Extract profile data organized by group for display in intention form"""
    groups = {}

    # Housing
    housing_parts = []
    if profile.get('pd:HousingOwnership'):
        housing_parts.append(profile['pd:HousingOwnership'])
    if profile.get('mysolido:housingType'):
        housing_parts.append(profile['mysolido:housingType'])
    if profile.get('pd:Location'):
        housing_parts.append(profile['pd:Location'])
    groups['housing'] = {
        'label': 'Woonsituatie',
        'icon': '\U0001f3e0',
        'filled': bool(housing_parts),
        'summary': ', '.join(housing_parts),
        'data': {
            'ownership': profile.get('pd:HousingOwnership', ''),
            'type': profile.get('mysolido:housingType', ''),
            'region': profile.get('pd:Location', ''),
        }
    }

    # Household
    household_parts = []
    household_data = {}
    if profile.get('pd:HouseholdSize'):
        household_parts.append(f"{profile['pd:HouseholdSize']} personen")
        household_data['size'] = profile['pd:HouseholdSize']
    family = profile.get('pd:FamilyStructure', {})
    children = family.get('children', [])
    if children:
        ages = [c.get('ageCategory', '') for c in children]
        household_parts.append(f"{len(children)} kind(eren): {', '.join(ages)}")
        household_data['children'] = children
    groups['household'] = {
        'label': 'Gezin',
        'icon': '\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466',
        'filled': bool(household_parts),
        'summary': ', '.join(household_parts),
        'data': household_data
    }

    # Vehicle
    vehicles = profile.get('pd:Vehicle', [])
    vehicle = vehicles[0] if vehicles else {}
    vehicle_parts = []
    if vehicle.get('type'):
        vehicle_parts.append(vehicle['type'])
    if vehicle.get('fuel'):
        vehicle_parts.append(vehicle['fuel'])
    if vehicle.get('yearBuilt'):
        vehicle_parts.append(str(vehicle['yearBuilt']))
    groups['vehicle'] = {
        'label': 'Voertuigen',
        'icon': '\U0001f697',
        'filled': bool(vehicle_parts),
        'summary': ', '.join(vehicle_parts),
        'data': vehicle
    }

    # Insurance
    insurances = profile.get('pd:Insurance', [])
    ins_parts = []
    for ins in insurances:
        parts = []
        if ins.get('type'):
            parts.append(ins['type'])
        if ins.get('provider'):
            parts.append(ins['provider'])
        if parts:
            ins_parts.append(' - '.join(parts))
    groups['insurance'] = {
        'label': 'Verzekeringen',
        'icon': '\U0001f6e1\ufe0f',
        'filled': bool(ins_parts),
        'summary': '; '.join(ins_parts),
        'data': insurances
    }

    # Occupation
    occupation = profile.get('pd:Occupation', {})
    occ_parts = []
    if occupation.get('sector'):
        occ_parts.append(occupation['sector'])
    if occupation.get('employmentType'):
        occ_parts.append(occupation['employmentType'])
    groups['occupation'] = {
        'label': 'Werk',
        'icon': '\U0001f4bc',
        'filled': bool(occ_parts),
        'summary': ', '.join(occ_parts),
        'data': occupation
    }

    # Health (only smokingStatus, not gpPractice)
    health = profile.get('pd:HealthData', {})
    health_parts = []
    health_data = {}
    if health.get('smokingStatus'):
        smoking_labels = {'ja': 'roker', 'nee': 'niet-roker', 'gestopt': 'gestopt met roken'}
        health_parts.append(smoking_labels.get(health['smokingStatus'], health['smokingStatus']))
        health_data['smokingStatus'] = health['smokingStatus']
    groups['health'] = {
        'label': 'Gezondheid',
        'icon': '\u2764\ufe0f',
        'filled': bool(health_parts),
        'summary': ', '.join(health_parts),
        'data': health_data
    }

    return groups


def load_all_intentions():
    """Load all intention records from the intenties folder"""
    intenties_dir = get_intenties_dir()
    if not intenties_dir or not os.path.isdir(intenties_dir):
        return []

    intentions = []
    for fname in os.listdir(intenties_dir):
        if fname.endswith('.jsonld') and not fname.startswith('.'):
            fpath = os.path.join(intenties_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    record = _json.load(f)
                record['_id'] = fname.replace('.jsonld', '')
                intentions.append(record)
            except (_json.JSONDecodeError, IOError):
                continue

    intentions.sort(key=lambda r: r.get('schema:dateCreated', ''), reverse=True)
    return intentions


def check_expired_intentions(intentions):
    """Check and update expired intentions, returns updated list"""
    now = datetime.now(timezone.utc)
    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        return intentions

    for intention in intentions:
        if intention.get('mysolido:status') != 'actief':
            continue
        valid_through = intention.get('schema:validThrough', '')
        if not valid_through:
            continue
        try:
            exp_dt = datetime.fromisoformat(valid_through)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < now:
                intention['mysolido:status'] = 'verlopen'
                fpath = os.path.join(intenties_dir, f"{intention['_id']}.jsonld")
                save_data = {k: v for k, v in intention.items() if not k.startswith('_')}
                with open(fpath, 'w', encoding='utf-8') as f:
                    _json.dump(save_data, f, indent=2, ensure_ascii=False)
        except (ValueError, TypeError):
            continue

    return intentions


def ensure_intenties_policy():
    """Create ODRL policy for intenties folder if it doesn't exist"""
    if not pod_exists('intenties/.policy.jsonld'):
        policy = {
            "@context": [
                "http://www.w3.org/ns/odrl.jsonld",
                {"dpv": "https://w3id.org/dpv#"}
            ],
            "@type": "Set",
            "uid": "urn:mysolido:policy:intenties",
            "profile": "http://www.w3.org/ns/odrl/2/core",
            "permission": [{
                "target": "urn:mysolido:container:intenties",
                "assignee": "urn:mysolido:owner",
                "action": ["read", "write", "delete"]
            }],
            "prohibition": [{
                "target": "urn:mysolido:container:intenties",
                "action": "distribute"
            }]
        }
        pod_mkdir('intenties')
        pod_write('intenties/.policy.jsonld',
                  _json.dumps(policy, indent=2, ensure_ascii=False))


@app.route('/intenties')
def intenties_overview():
    """Overview of all intentions"""
    intentions = load_all_intentions()
    intentions = check_expired_intentions(intentions)

    # Enrich with display data
    status_filter = request.args.get('status', 'alle')
    enriched = []
    for intent in intentions:
        cat_key = intent.get('mysolido:category', 'anders')
        cat_info = INTENTION_CATEGORIES.get(cat_key, INTENTION_CATEGORIES['anders'])
        intent['_icon'] = cat_info['icon']
        intent['_category_label'] = cat_info['label']
        intent['_status'] = intent.get('mysolido:status', 'concept')
        intent['_date'] = intent.get('schema:dateCreated', '')[:10]
        intent['_description'] = intent.get('schema:description', '')

        if status_filter == 'alle' or intent['_status'] == status_filter:
            enriched.append(intent)

    return render_template('intenties.html',
        intentions=enriched,
        status_filter=status_filter,
    )


@app.route('/intenties/nieuw', methods=['GET', 'POST'])
def intentie_new():
    """Create a new intention"""
    if BRIDGE_MODE:
        flash('Niet beschikbaar in Bridge-modus', 'error')
        return redirect(url_for('intenties_overview'))

    if request.method == 'POST':
        category = request.form.get('category', 'anders')
        description = request.form.get('description', '').strip()
        validity = request.form.get('validity', '1m')

        if not description:
            flash('Omschrijving is verplicht', 'error')
            return redirect(url_for('intentie_new'))

        cat_info = INTENTION_CATEGORIES.get(category, INTENTION_CATEGORIES['anders'])
        val_info = VALIDITY_OPTIONS.get(validity, VALIDITY_OPTIONS['1m'])

        now = datetime.now(timezone.utc)
        valid_through = now + timedelta(days=val_info['days'])
        intention_id = str(uuid.uuid4())

        # Build shared profile data
        profile = load_profile_data()
        profile_groups = extract_profile_groups(profile)
        shared_data = {}
        selected_fields = request.form.getlist('profile_fields')

        for group_key, group_info in profile_groups.items():
            shared_data[group_key] = {
                'included': group_key in selected_fields,
            }
            if group_key in selected_fields and group_info['filled']:
                shared_data[group_key]['data'] = group_info['data']

        record = {
            "@context": {
                "mysolido": "https://mysolido.com/vocab#",
                "dpv": "https://w3id.org/dpv#",
                "schema": "https://schema.org/",
                "xsd": "http://www.w3.org/2001/XMLSchema#"
            },
            "@type": "mysolido:Intention",
            "@id": f"urn:mysolido:intention:{intention_id}",
            "mysolido:category": category,
            "mysolido:categoryLabel": cat_info['label'],
            "schema:description": description,
            "mysolido:status": "concept",
            "schema:dateCreated": now.isoformat(),
            "schema:validThrough": valid_through.isoformat(),
            "mysolido:sharedProfileData": shared_data,
        }

        pod_mkdir('intenties')
        pod_write(f'intenties/{intention_id}.jsonld',
                  _json.dumps(record, indent=2, ensure_ascii=False))
        ensure_intenties_policy()

        flash(f'Intentie "{cat_info["label"]}" opgeslagen als concept', 'success')
        log_action('intention_create', {'id': intention_id, 'category': category})
        return redirect(url_for('intenties_overview'))

    # GET: show form
    profile = load_profile_data()
    profile_groups = extract_profile_groups(profile)

    return render_template('intentie_nieuw.html',
        categories=INTENTION_CATEGORIES,
        validity_options=VALIDITY_OPTIONS,
        profile_groups=profile_groups,
    )


@app.route('/intenties/<intention_id>')
def intentie_detail(intention_id):
    """View a single intention"""
    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash('Intenties-map niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Intentie niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['_id'] = intention_id
    cat_key = record.get('mysolido:category', 'anders')
    cat_info = INTENTION_CATEGORIES.get(cat_key, INTENTION_CATEGORIES['anders'])
    record['_icon'] = cat_info['icon']
    record['_category_label'] = cat_info['label']
    record['_status'] = record.get('mysolido:status', 'concept')

    # Load current profile data for display
    profile = load_profile_data()
    profile_groups = extract_profile_groups(profile)

    return render_template('intentie_detail.html',
        intention=record,
        profile_groups=profile_groups,
        read_only=BRIDGE_MODE,
    )


@app.route('/intenties/<intention_id>/activate', methods=['POST'])
def intentie_activate(intention_id):
    """Activate an intention"""
    if BRIDGE_MODE:
        abort(403)

    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash('Intenties-map niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Intentie niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['mysolido:status'] = 'actief'
    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=2, ensure_ascii=False)

    flash('Intentie geactiveerd', 'success')
    log_action('intention_activate', {'id': intention_id})
    return redirect(url_for('intentie_detail', intention_id=intention_id))


@app.route('/intenties/<intention_id>/withdraw', methods=['POST'])
def intentie_withdraw(intention_id):
    """Withdraw an intention"""
    if BRIDGE_MODE:
        abort(403)

    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash('Intenties-map niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Intentie niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['mysolido:status'] = 'ingetrokken'
    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=2, ensure_ascii=False)

    flash('Intentie ingetrokken', 'success')
    log_action('intention_withdraw', {'id': intention_id})
    return redirect(url_for('intentie_detail', intention_id=intention_id))


@app.route('/intenties/<intention_id>/delete', methods=['POST'])
def intentie_delete(intention_id):
    """Delete an intention"""
    if BRIDGE_MODE:
        abort(403)

    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash('Intenties-map niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Intentie niet gevonden', 'error')
        return redirect(url_for('intenties_overview'))

    os.remove(fpath)
    flash('Intentie verwijderd', 'success')
    log_action('intention_delete', {'id': intention_id})
    return redirect(url_for('intenties_overview'))


# === CONSENT REQUEST MODULE (Fase 3 — verzoeken van buitenaf) ===

REQUEST_CATEGORIES = {
    'verzekeringen': {'label': 'Verzekeringen', 'description': 'Ik wil een verzekeringsaanbod doen'},
    'financieel': {'label': 'Financieel advies', 'description': 'Ik wil financieel advies geven'},
    'zorg': {'label': 'Zorg', 'description': 'Ik heb medische gegevens nodig'},
    'juridisch': {'label': 'Juridisch', 'description': 'Ik heb juridische documenten nodig'},
    'anders': {'label': 'Anders', 'description': 'Anders (toelichting hieronder)'},
}

APPROVAL_VALIDITY = {
    '1d': {'label': '1 dag', 'days': 1},
    '1w': {'label': '1 week', 'days': 7},
    '1m': {'label': '1 maand', 'days': 30},
    '3m': {'label': '3 maanden', 'days': 90},
}

# Simple in-memory rate limiter: {ip: [timestamp, ...]}
_request_rate_limit = {}


def is_rate_limited(ip, max_requests=10, window_seconds=3600):
    """Check and enforce rate limit: max requests per window per IP"""
    now = time.time()
    timestamps = _request_rate_limit.get(ip, [])
    # Remove old timestamps
    timestamps = [t for t in timestamps if now - t < window_seconds]
    if len(timestamps) >= max_requests:
        _request_rate_limit[ip] = timestamps
        return True
    timestamps.append(now)
    _request_rate_limit[ip] = timestamps
    return False


def get_verzoeken_dir():
    """Return the absolute path to the verzoeken folder"""
    return safe_pod_path('verzoeken')


def load_all_requests():
    """Load all consent request records from the verzoeken folder"""
    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir or not os.path.isdir(verzoeken_dir):
        return []

    requests_list = []
    for fname in os.listdir(verzoeken_dir):
        if fname.endswith('.jsonld') and not fname.startswith('.'):
            fpath = os.path.join(verzoeken_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    record = _json.load(f)
                record['_id'] = fname.replace('.jsonld', '')
                requests_list.append(record)
            except (_json.JSONDecodeError, IOError):
                continue

    requests_list.sort(key=lambda r: r.get('schema:dateCreated', ''), reverse=True)
    return requests_list


def count_new_requests():
    """Count unhandled (new) requests for badge display"""
    try:
        reqs = load_all_requests()
        return sum(1 for r in reqs if r.get('mysolido:status') == 'nieuw')
    except Exception:
        return 0


def find_request_by_status_token(token):
    """Find a request record by its status token"""
    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir or not os.path.isdir(verzoeken_dir):
        return None, None

    for fname in os.listdir(verzoeken_dir):
        if fname.endswith('.jsonld') and not fname.startswith('.'):
            fpath = os.path.join(verzoeken_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    record = _json.load(f)
                if record.get('mysolido:statusToken') == token:
                    record['_id'] = fname.replace('.jsonld', '')
                    return record, fpath
            except (_json.JSONDecodeError, IOError):
                continue
    return None, None


def ensure_verzoeken_policy():
    """Create ODRL policy for verzoeken folder if it doesn't exist"""
    if not pod_exists('verzoeken/.policy.jsonld'):
        policy = {
            "@context": [
                "http://www.w3.org/ns/odrl.jsonld",
                {"dpv": "https://w3id.org/dpv#"}
            ],
            "@type": "Set",
            "uid": "urn:mysolido:policy:verzoeken",
            "profile": "http://www.w3.org/ns/odrl/2/core",
            "permission": [{
                "target": "urn:mysolido:container:verzoeken",
                "assignee": "urn:mysolido:owner",
                "action": ["read", "write", "delete"]
            }],
            "prohibition": [{
                "target": "urn:mysolido:container:verzoeken",
                "action": "distribute"
            }]
        }
        pod_mkdir('verzoeken')
        pod_write('verzoeken/.policy.jsonld',
                  _json.dumps(policy, indent=2, ensure_ascii=False))


def sanitize_input(value):
    """Strip HTML tags and trim whitespace from user input"""
    if not value:
        return ''
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', str(value))
    return clean.strip()


# --- Public routes (work on Bridge too, no login needed) ---

@app.route('/verzoek', methods=['GET'])
def verzoek_formulier():
    """Public consent request form"""
    return render_template('verzoek_formulier.html',
        categories=REQUEST_CATEGORIES,
    )


@app.route('/verzoek', methods=['POST'])
def verzoek_submit():
    """Submit a consent request (public, works on Bridge)"""
    # Rate limiting
    client_ip = request.remote_addr or 'unknown'
    if is_rate_limited(client_ip):
        flash('Te veel verzoeken. Probeer het later opnieuw.', 'error')
        return redirect(url_for('verzoek_formulier'))

    name = sanitize_input(request.form.get('name', ''))
    organization = sanitize_input(request.form.get('organization', ''))
    email = sanitize_input(request.form.get('email', ''))
    category = request.form.get('category', 'anders')
    purpose = sanitize_input(request.form.get('purpose', ''))
    requested_data = request.form.getlist('requested_data')
    agreed = request.form.get('agreed_terms') == 'yes'

    # Validation
    if not name or not email or not purpose:
        flash('Naam, e-mailadres en toelichting zijn verplicht.', 'error')
        return redirect(url_for('verzoek_formulier'))

    if not agreed:
        flash('U moet akkoord gaan met de voorwaarden.', 'error')
        return redirect(url_for('verzoek_formulier'))

    if not requested_data:
        flash('Selecteer ten minste één gegevensgroep.', 'error')
        return redirect(url_for('verzoek_formulier'))

    # Basic email validation
    if '@' not in email or '.' not in email:
        flash('Voer een geldig e-mailadres in.', 'error')
        return redirect(url_for('verzoek_formulier'))

    cat_info = REQUEST_CATEGORIES.get(category, REQUEST_CATEGORIES['anders'])
    request_id = str(uuid.uuid4())
    status_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    record = {
        "@context": {
            "mysolido": "https://mysolido.com/vocab#",
            "dpv": "https://w3id.org/dpv#",
            "schema": "https://schema.org/",
            "xsd": "http://www.w3.org/2001/XMLSchema#"
        },
        "@type": "mysolido:ConsentRequest",
        "@id": f"urn:mysolido:request:{request_id}",
        "mysolido:statusToken": status_token,
        "mysolido:status": "nieuw",
        "schema:dateCreated": now.isoformat(),
        "mysolido:requester": {
            "schema:name": name,
            "schema:worksFor": organization,
            "schema:email": email,
        },
        "mysolido:category": category,
        "mysolido:categoryLabel": cat_info['label'],
        "mysolido:requestedData": requested_data,
        "mysolido:purpose": purpose,
        "mysolido:agreedToTerms": True,
        "mysolido:approvedData": None,
        "mysolido:responseLink": None,
        "mysolido:validUntil": None,
        "mysolido:rejectionReason": None,
    }

    pod_mkdir('verzoeken')
    pod_write(f'verzoeken/{request_id}.jsonld',
              _json.dumps(record, indent=2, ensure_ascii=False))
    ensure_verzoeken_policy()

    return render_template('verzoek_bevestiging.html',
        status_token=status_token,
    )


@app.route('/verzoek/status/<status_token>')
def verzoek_status(status_token):
    """Public status page for a consent request"""
    record, _ = find_request_by_status_token(status_token)
    if not record:
        return render_template('verzoek_status.html', found=False), 404

    status = record.get('mysolido:status', 'nieuw')
    response_link = record.get('mysolido:responseLink')
    valid_until = record.get('mysolido:validUntil', '')

    # Check if approved response has expired
    if status == 'goedgekeurd' and valid_until:
        try:
            exp_dt = datetime.fromisoformat(valid_until)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                status = 'verlopen'
        except (ValueError, TypeError):
            pass

    return render_template('verzoek_status.html',
        found=True,
        status=status,
        response_link=response_link,
        valid_until=valid_until[:10] if valid_until else '',
        status_token=status_token,
    )


@app.route('/verzoek/response/<status_token>')
def verzoek_response(status_token):
    """Public page showing approved profile data"""
    record, _ = find_request_by_status_token(status_token)
    if not record:
        return render_template('verzoek_response.html', found=False), 404

    status = record.get('mysolido:status', 'nieuw')
    valid_until = record.get('mysolido:validUntil', '')

    if status != 'goedgekeurd':
        return render_template('verzoek_response.html', found=False), 404

    # Check expiry
    if valid_until:
        try:
            exp_dt = datetime.fromisoformat(valid_until)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                return render_template('verzoek_response.html', found=True, expired=True,
                                       valid_until=valid_until[:10])
        except (ValueError, TypeError):
            pass

    # Load the response data
    request_id = record['_id']
    response_path = safe_pod_path(f'verzoeken/{request_id}_response.json')
    if not response_path or not os.path.exists(response_path):
        return render_template('verzoek_response.html', found=False), 404

    with open(response_path, 'r', encoding='utf-8') as f:
        response_data = _json.load(f)

    return render_template('verzoek_response.html',
        found=True,
        expired=False,
        response_data=response_data,
        valid_until=valid_until[:10] if valid_until else '',
    )


# --- Owner routes (local only, blocked on Bridge) ---

@app.route('/verzoeken')
def verzoeken_overview():
    """Overview of all incoming consent requests (owner only)"""
    if BRIDGE_MODE:
        abort(403)

    requests_list = load_all_requests()

    # Enrich for display
    for req in requests_list:
        req['_status'] = req.get('mysolido:status', 'nieuw')
        requester = req.get('mysolido:requester', {})
        req['_name'] = requester.get('schema:name', 'Onbekend')
        req['_organization'] = requester.get('schema:worksFor', '')
        req['_category_label'] = req.get('mysolido:categoryLabel', 'Anders')
        req['_date'] = req.get('schema:dateCreated', '')[:10]
        req['_requested_data'] = req.get('mysolido:requestedData', [])

    return render_template('verzoeken.html', requests=requests_list)


@app.route('/verzoeken/<request_id>')
def verzoek_detail_owner(request_id):
    """Detail view of a consent request (owner only)"""
    if BRIDGE_MODE:
        abort(403)

    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir:
        flash('Verzoeken-map niet gevonden', 'error')
        return redirect(url_for('verzoeken_overview'))

    fpath = os.path.join(verzoeken_dir, f"{request_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Verzoek niet gevonden', 'error')
        return redirect(url_for('verzoeken_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['_id'] = request_id
    record['_status'] = record.get('mysolido:status', 'nieuw')

    # Load profile data for approval form
    profile = load_profile_data()
    profile_groups = extract_profile_groups(profile)

    return render_template('verzoek_detail.html',
        req=record,
        profile_groups=profile_groups,
        approval_validity=APPROVAL_VALIDITY,
    )


@app.route('/verzoeken/<request_id>/approve', methods=['POST'])
def verzoek_approve(request_id):
    """Approve a consent request (owner only)"""
    if BRIDGE_MODE:
        abort(403)

    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir:
        flash('Verzoeken-map niet gevonden', 'error')
        return redirect(url_for('verzoeken_overview'))

    fpath = os.path.join(verzoeken_dir, f"{request_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Verzoek niet gevonden', 'error')
        return redirect(url_for('verzoeken_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    # Get approved data groups from form
    approved_groups = request.form.getlist('approved_data')
    validity_key = request.form.get('validity', '1w')
    val_info = APPROVAL_VALIDITY.get(validity_key, APPROVAL_VALIDITY['1w'])

    if not approved_groups:
        flash('Selecteer ten minste één gegevensgroep om te delen.', 'error')
        return redirect(url_for('verzoek_detail_owner', request_id=request_id))

    # Build response data with only approved profile groups
    profile = load_profile_data()
    profile_groups = extract_profile_groups(profile)
    response_data = {}

    for group_key in approved_groups:
        group = profile_groups.get(group_key)
        if group and group['filled']:
            response_data[group_key] = {
                'label': group['label'],
                'data': group['data'],
            }

    # Save response JSON
    pod_write(f'verzoeken/{request_id}_response.json',
              _json.dumps(response_data, indent=2, ensure_ascii=False))

    # Update request record
    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(days=val_info['days'])
    status_token = record.get('mysolido:statusToken', '')

    record['mysolido:status'] = 'goedgekeurd'
    record['mysolido:approvedData'] = approved_groups
    record['mysolido:responseLink'] = f'/verzoek/response/{status_token}'
    record['mysolido:validUntil'] = valid_until.isoformat()

    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=2, ensure_ascii=False)

    # Create consent record (using existing consent module pattern)
    requester = record.get('mysolido:requester', {})
    requester_name = requester.get('schema:name', 'Onbekend')
    requester_org = requester.get('schema:worksFor', '')
    receiver_label = f"{requester_name} ({requester_org})" if requester_org else requester_name

    flash(f'Verzoek van {receiver_label} goedgekeurd.', 'success')
    log_action('request_approve', {
        'id': request_id,
        'requester': requester_name,
        'approved_data': approved_groups,
        'valid_until': valid_until.isoformat(),
    })
    return redirect(url_for('verzoek_detail_owner', request_id=request_id))


@app.route('/verzoeken/<request_id>/reject', methods=['POST'])
def verzoek_reject(request_id):
    """Reject a consent request (owner only)"""
    if BRIDGE_MODE:
        abort(403)

    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir:
        flash('Verzoeken-map niet gevonden', 'error')
        return redirect(url_for('verzoeken_overview'))

    fpath = os.path.join(verzoeken_dir, f"{request_id}.jsonld")
    if not os.path.exists(fpath):
        flash('Verzoek niet gevonden', 'error')
        return redirect(url_for('verzoeken_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    reason = sanitize_input(request.form.get('reason', ''))
    record['mysolido:status'] = 'afgewezen'
    if reason:
        record['mysolido:rejectionReason'] = reason

    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=2, ensure_ascii=False)

    requester = record.get('mysolido:requester', {})
    requester_name = requester.get('schema:name', 'Onbekend')
    flash(f'Verzoek van {requester_name} afgewezen.', 'success')
    log_action('request_reject', {'id': request_id, 'requester': requester_name})
    return redirect(url_for('verzoeken_overview'))


if __name__ == '__main__':
    print()

    # Migreer plain text wachtwoorden naar bcrypt
    migrate_passwords_to_bcrypt()

    if BRIDGE_MODE:
        bridge_pw = os.getenv('BRIDGE_PASSWORD', os.getenv('CSS_PASSWORD', ''))
        print("  === MySolido Bridge ===")
        print("  [BRIDGE] Read-only modus")
        print(f"  Pod: {SOLID_POD_URL}")
        if bridge_pw:
            print(f"  Wachtwoord: beveiligd met bcrypt")
        else:
            print("  [WAARSCHUWING] Geen BRIDGE_PASSWORD of CSS_PASSWORD ingesteld!")
        print(f"  Start op http://127.0.0.1:5000")
        print("  ========================")
        print()
        app.run(port=5000, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
    else:
        print("  === MySolido ===")

        if not auto_setup():
            print()
            print("  Setup mislukt. Zorg dat Community Solid Server draait op poort 3000:")
            print("  npx @solid/community-server -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json")
            print()
            exit(1)

        # Initialize default ODRL policies for all standard folders
        init_default_policies()

        # Clean up old watermark temp files
        cleanup_temp_files()

        print()
        print(f"  Pod: {os.getenv('SOLID_POD_URL')}")
        print(f"  Start op http://localhost:5000")
        print("  ================")
        print()

        app.run(port=5000, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
