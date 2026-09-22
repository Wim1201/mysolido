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
from translations import get_translations, t as translate
from sync_bridge import (
    BRIDGE_AUTO_SYNC as bridge_auto_sync_enabled,
    is_configured as bridge_sync_configured,
    get_status as get_bridge_sync_status,
    sync_in_background,
    auto_sync_after_change
)
from watermark import watermark_pdf, watermark_image, get_watermark_text
import platform
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

# === VERSIEREGEL (MyTerms-demo, subtaak 5) ===
# Korte commit-hash bij opstart, met VERSION als terugval als git ontbreekt; in de voettekst
# van elke pagina samen met "Bridge" of "lokaal", zodat op de telefoon te zien is welke code draait.
VERSION = '1.4.0-myterms'


def _git_short_hash():
    try:
        import subprocess as _sp
        out = _sp.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=PROJECT_DIR,
                      capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else ''
    except Exception:
        return ''


APP_VERSION = _git_short_hash() or VERSION
APP_MODE = 'Bridge' if BRIDGE_MODE else 'lokaal'
APP_PORT = int(os.getenv('MYSOLIDO_PORT', '5000'))   # tweede proces (bijv. --bridge naast lokaal) op een andere poort

# === OPENBARE ROUTES OP DE BRIDGE (21-09-2026) ===
# check_bridge_auth() staat in Bridge-modus standaard dicht: elk verzoek zonder eigenaarssessie gaat naar
# /bridge-login, behalve de endpointnamen hieronder. Per regel de reden. Een nieuwe route die hier niet
# staat, valt dus vanzelf dicht; regressietest 13h loopt over app.url_map en bewaakt dat.
# Nooit openbaar: Agreement-JSON (/verzoeken/<id>/agreement.jsonld), consentrecords en alles onder /verzoeken.
BRIDGE_PUBLIC_ENDPOINTS = {
    'bridge_login':         'het inlogscherm zelf (GET en POST /bridge-login)',
    'static':               "css, js en iconen; ook het inlogscherm en de openbare pagina's hebben ze nodig",
    'view_shared_file':     '/share/<token>: deellink voor een ontvanger; het token en het eigen wachtwoord van de link beschermen de inhoud',
    'verzoek_formulier':    'GET /verzoek: vrij verzoekformulier voor een wederpartij',
    'verzoek_submit':       'POST /verzoek: indienen van dat verzoek (rate limit per IP)',
    'verzoek_status':       '/verzoek/status/<token>: statuspagina van de wederpartij, alleen met het geheime statustoken',
    'verzoek_response':     '/verzoek/response/<token>: vrijgegeven gegevens voor de wederpartij, alleen met het geheime statustoken',
    'verzoek_intentie':     'GET/POST /verzoek/intentie/<id>: voorwaarden van een intentie lezen; accepteren blokkeert de route zelf op de Bridge',
    'crash_report_receive': 'POST /crash-report: anonieme crashmelding van een lokale MySolido, zonder sessie',
    'intentie_policy_file': '/intenties/<id>/policy.jsonld: de Offer machineleesbaar (MyTerms), ALLEEN bij status actief; '
                            'concept, ingetrokken en verlopen blijven achter de inlog (zie bridge_endpoint_is_public)',
}

# Ensure temp directory exists
os.makedirs(TEMP_DIR, exist_ok=True)


def flash_t(key, category='success', **kwargs):
    """Flash een vertaalde melding"""
    lang = session.get('language', 'nl')
    translations = get_translations(lang)
    text = translations.get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    flash(text, category)


def is_watermark_enabled():
    """Check if watermarking is enabled (default: True)"""
    return os.getenv('WATERMARK_ENABLED', 'true').lower() in ('true', '1', 'yes')


def is_crash_reporting_enabled():
    """Check if anonymous crash reporting is enabled (default: False, opt-in)"""
    return os.getenv('CRASH_REPORTING', 'false').lower() in ('true', '1', 'yes')


# PRIVACY: send_crash_report() sends ONLY:
# - MySolido version number
# - Operating system (Windows/Mac/Linux) + version
# - Python version
# - Error type and error message (max 500 chars)
# - Context (max 200 chars, e.g. "bestand uploaden")
#
# It NEVER sends:
# - Name, email, IP address
# - File names or pod contents
# - Path information or folder names
# - Network data or location
def send_crash_report(error_type, error_message, context=""):
    """Send an anonymous crash report to the Bridge (if enabled)"""
    try:
        if not is_crash_reporting_enabled():
            return

        bridge_url = os.getenv('SHARE_BASE_URL', '')
        if not bridge_url:
            return

        report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": "1.2.0",
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
            "error_type": str(error_type)[:200],
            "error_message": str(error_message)[:500],
            "context": str(context)[:200],
        }

        requests.post(
            f"{bridge_url}/crash-report",
            json=report,
            timeout=5
        )
    except Exception:
        pass  # Silent fail — crash reporting must never break the app


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
    # Tekst altijd als UTF-8 schrijven: alle lezers openen met encoding='utf-8'; zonder deze
    # parameter schreef Windows cp1252 en brak elk record met een niet-ASCII-teken (20-09-2026)
    with open(full_path, mode, encoding=None if mode == 'wb' else 'utf-8') as f:
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
            # Skip metadata bestanden en ODRL-documenten naast records (<uuid>.policy.jsonld, <uuid>.agreement.jsonld)
            if entry.endswith(('.acl', '.meta', '.policy.jsonld', '.agreement.jsonld')):
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
        if entry.startswith('.') or entry.endswith(('.acl', '.meta', '.policy.jsonld', '.agreement.jsonld')):
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
        # Skip verborgen mappen en _trash
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '_trash']
        # Bepaal of we in een systeemmap zitten
        rel = os.path.relpath(root, pod_path)
        top_folder = rel.split(os.sep)[0] if rel != '.' else None
        in_system_folder = top_folder in SYSTEM_FOLDERS
        # Tel systeemmappen zelf niet mee, en ook hun submappen niet
        if in_system_folder:
            pass  # skip counting for system folders
        else:
            # Exclude system folders from the count at top level
            if rel == '.':
                countable = [d for d in dirs if d not in SYSTEM_FOLDERS]
            else:
                countable = []
            total_folders += len(countable)
        for f in files:
            if not f.startswith('.') and not f.endswith(('.acl', '.meta', '.policy.jsonld', '.agreement.jsonld')):
                filepath = os.path.join(root, f)
                size = os.path.getsize(filepath)
                total_size += size
                mtime = os.path.getmtime(filepath)
                if latest_modified is None or mtime > latest_modified:
                    latest_modified = mtime
                if not in_system_folder:
                    total_files += 1

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
            if is_bcrypt_hash(os.getenv('CSS_PASSWORD', '')):
                print("  [LET OP] CSS_PASSWORD in .env is een bcrypt-hash (legacy).")
                print("           Voor externe Solid-app login: wijzig het wachtwoord")
                print("           via de Profile-pagina, of verwijder .env + .data/ voor")
                print("           een volledig verse setup.")
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
        send_crash_report("auto_setup_failed", str(e), "eerste keer opstarten")
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

# System folders — excluded from dashboard stats, recent uploads, and folder grid
SYSTEM_FOLDERS = {'profiel', 'profile', 'intenties', 'verzoeken', 'toestemmingen', 'consent', '_trash'}

# Default folders to create on init
DEFAULT_FOLDERS = [
    'identiteit', 'medisch', 'financieel', 'wonen', 'zakelijk',
    'werk', 'voertuigen', 'juridisch', 'media', 'accounts',
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
}


def bridge_endpoint_is_public(endpoint, view_args):
    """Staat dit endpoint op BRIDGE_PUBLIC_ENDPOINTS, inclusief de voorwaarde voor de Offer-JSON?

    De Offer (policy.jsonld) is alleen openbaar zolang de intentie de status 'actief' heeft: de Offer
    bevat geen profielwaarden en de openbare voorwaardenpagina toont dezelfde JSON al. Een concept,
    ingetrokken of verlopen intentie (of een onbekend id) blijft achter de inlog.
    """
    if endpoint not in BRIDGE_PUBLIC_ENDPOINTS:
        return False
    if endpoint == 'intentie_policy_file':
        record = load_intention_record((view_args or {}).get('intention_id', '')) or {}
        return record.get('mysolido:status') == 'actief'
    return True


@app.before_request
def check_bridge_auth():
    """Bridge-modus: standaard dicht, alleen BRIDGE_PUBLIC_ENDPOINTS zonder eigenaarssessie."""
    if not BRIDGE_MODE:
        return

    if bridge_endpoint_is_public(request.endpoint, request.view_args):
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
        'ai_chat',
        'ai_ask',
        'ai_index',
        'ai_status',
    ]

    if request.endpoint in blocked_endpoints:
        flash_t('flash_bridge_readonly', 'error')
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
    lang = session.get('language', 'nl')
    return {
        'folder_icons': FOLDER_ICONS,
        'unread_count': get_unread_count(),
        'new_requests_count': count_new_requests(),
        'active_nav': active,
        'bridge_mode': BRIDGE_MODE,
        'bridge_sync_configured': bridge_sync_configured(),
        'bridge_sync_status': get_bridge_sync_status(),
        'bridge_auto_sync': bridge_auto_sync_enabled,   # B7: eerlijke weergave van de .env-instelling
        't': get_translations(lang),
        'current_lang': lang,
        'app_version': APP_VERSION,   # voettekst (subtaak 5)
        'app_mode': APP_MODE,
    }


@app.route('/settings/language', methods=['POST'])
def change_language():
    lang = request.form.get('language', 'nl')
    if lang in ('nl', 'en'):
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))


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
            flash_t('flash_wrong_password', 'error')

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
        flash_t('flash_sync_not_configured', 'error')
        return redirect(url_for('profile'))

    sync_in_background()
    flash_t('flash_sync_started')
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
    """Get recent file uploads from audit log, excluding system folders"""
    log = get_audit_log('upload', limit=limit * 3)
    filtered = [e for e in log if e.get('details', {}).get('folder', '').split('/')[0] not in SYSTEM_FOLDERS]
    return filtered[:limit]


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
        flash_t('flash_access_expired', 'success', webid=display_webid, name=resource_name)
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
        flash_t('flash_no_file_selected', 'error')
        return redirect_to_folder(folder_path)

    file = request.files['file']
    if file.filename == '':
        flash_t('flash_no_file_selected', 'error')
        return redirect_to_folder(folder_path)

    if folder_path:
        relative_path = folder_path + '/' + file.filename
    else:
        relative_path = file.filename

    try:
        if pod_write(relative_path, file.read()):
            flash_t('flash_upload_success', 'success', filename=file.filename)
            log_action('upload', {'file': file.filename, 'folder': folder_path or 'root'})
            auto_sync_after_change()
        else:
            flash_t('flash_upload_failed_save', 'error')
    except Exception as e:
        send_crash_report("upload_failed", str(e), "bestand uploaden")
        flash_t('flash_upload_failed', 'error')

    return redirect_to_folder(folder_path)


@app.route('/delete', methods=['POST'])
def delete():
    """Verplaats een resource naar de prullenbak"""
    resource_url = request.form.get('resource_url')
    folder_path = request.form.get('folder_path', '').strip('/')

    if not resource_url:
        flash_t('flash_no_resource', 'error')
        return redirect_to_folder(folder_path)

    name = resource_url.rstrip('/').split('/')[-1]
    is_folder = resource_url.endswith('/')

    if is_folder:
        # Folders: direct verwijderen (niet naar prullenbak)
        rel_path = url_to_relative_path(resource_url)
        if rel_path and pod_delete(rel_path):
            flash_t('flash_folder_deleted', 'success', name=name)
            log_action('delete', {'resource': name, 'folder': folder_path or 'root'})
            auto_sync_after_change()
        else:
            flash_t('flash_delete_failed', 'error')
        return redirect_to_folder(folder_path)

    # Files: verplaats naar prullenbak via filesystem
    # Step 1: Ensure _trash/ directory exists
    pod_mkdir('_trash')

    # Step 2: Read the file from filesystem
    rel_path = url_to_relative_path(resource_url)
    if not rel_path:
        flash_t('flash_delete_invalid_path', 'error')
        return redirect_to_folder(folder_path)

    src_path = safe_pod_path(rel_path)
    if not src_path or not os.path.isfile(src_path):
        flash_t('flash_delete_not_found', 'error')
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
        flash_t('flash_trash_failed', 'error')
        return redirect_to_folder(folder_path)

    shutil.copy2(src_path, dst_path)

    # Step 5: Delete original
    os.remove(src_path)

    # Step 6: Record in trash.json
    resource_path = folder_path + '/' + name if folder_path else name
    move_to_trash(resource_url, resource_path, name, folder_path or 'root', trash_url)

    flash_t('flash_trash_success', 'success', name=name)
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
        flash_t('flash_invalid_folder_name', 'error')
        return redirect_to_folder(folder_path)

    if folder_path:
        relative_path = folder_path + '/' + normalized
    else:
        relative_path = normalized

    if pod_exists(relative_path):
        flash_t('flash_folder_exists', 'error', name=normalized)
        return redirect_to_folder(folder_path)

    if pod_mkdir(relative_path):
        flash_t('flash_folder_created', 'success', name=normalized)
        log_action('create_folder', {'name': normalized, 'path': folder_path or 'root'})
        auto_sync_after_change()
    else:
        flash_t('flash_folder_create_failed', 'error')

    return redirect_to_folder(folder_path)


@app.route('/move', methods=['POST'])
def move():
    """Verplaats een bestand naar een andere map"""
    resource_url = request.form.get('resource_url', '')
    target_folder = request.form.get('target_folder', '').strip('/')
    folder_path = request.form.get('folder_path', '').strip('/')
    filename = resource_url.rstrip('/').split('/')[-1]

    if not resource_url or not filename:
        flash_t('flash_no_file_specified', 'error')
        return redirect_to_folder(folder_path)

    src_rel = url_to_relative_path(resource_url)
    if target_folder:
        dst_rel = target_folder + '/' + filename
    else:
        dst_rel = filename

    if src_rel == dst_rel:
        flash_t('flash_already_in_folder', 'error')
        return redirect_to_folder(folder_path)

    src_path = safe_pod_path(src_rel) if src_rel else None
    dst_path = safe_pod_path(dst_rel)

    if not src_path or not os.path.isfile(src_path):
        flash_t('flash_move_not_found', 'error')
        return redirect_to_folder(folder_path)

    if not dst_path:
        flash_t('flash_move_invalid_target', 'error')
        return redirect_to_folder(folder_path)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.move(src_path, dst_path)

    target_label = target_folder if target_folder else 'Pod root'
    flash_t('flash_move_success', 'success', filename=filename, target=target_label)
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
        flash_t('flash_file_open_failed', 'error')
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
        flash_t('flash_file_download_failed', 'error')
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
        flash_t('flash_no_resource', 'error')
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
        flash_t('flash_fill_webid', 'error')
        return redirect_to_folder(folder_path)

    try:
        add_share(resource_url, resource_path, webid, modes, expires)
        write_acl(resource_url)

        resource_name = resource_url.rstrip('/').split('/')[-1]
        display_webid = 'iedereen (openbaar)' if webid == 'public' else webid
        flash_t('flash_share_success', 'success', name=resource_name, webid=display_webid)
        log_action('share', {'resource': resource_path, 'webid': webid, 'modes': modes})
    except Exception as e:
        send_crash_report("share_failed", str(e), "deellink aanmaken")
        flash_t('flash_share_failed', 'error')

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
        flash_t('flash_file_not_found', 'error')
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
            flash_t('flash_wrong_password', 'error')
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
        flash_t('flash_link_revoked')
        log_action('share_link_revoked', {'link_id': link_id})
        auto_sync_after_change()
    else:
        flash_t('flash_link_not_found', 'error')
    return redirect(url_for('shares_overview'))


@app.route('/revoke', methods=['POST'])
def revoke():
    """Revoke access for a specific WebID to a resource"""
    resource_url = request.form.get('resource_url', '')
    webid = request.form.get('webid', '')
    resource_path = request.form.get('resource_path', '')

    if not resource_url or not webid:
        flash_t('flash_invalid_request', 'error')
        return redirect(url_for('shares_overview'))

    remove_share(resource_url, webid)
    write_acl(resource_url)

    resource_name = resource_url.rstrip('/').split('/')[-1]
    display_webid = 'iedereen (openbaar)' if webid == 'public' else webid
    flash_t('flash_access_revoked', 'success', webid=display_webid, name=resource_name)
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
        flash_t('flash_trash_item_not_found', 'error')
        return redirect(url_for('trash_overview'))

    # Move from _trash/ back to original location via filesystem
    trash_rel = url_to_relative_path(entry['trash_url'])
    orig_rel = url_to_relative_path(entry['resource_url'])

    if not trash_rel or not orig_rel:
        flash_t('flash_restore_invalid_path', 'error')
        return redirect(url_for('trash_overview'))

    trash_path = safe_pod_path(trash_rel)
    orig_path = safe_pod_path(orig_rel)

    if not trash_path or not os.path.isfile(trash_path):
        flash_t('flash_restore_not_found', 'error')
        return redirect(url_for('trash_overview'))

    if not orig_path:
        flash_t('flash_restore_invalid_target', 'error')
        return redirect(url_for('trash_overview'))

    os.makedirs(os.path.dirname(orig_path), exist_ok=True)
    shutil.move(trash_path, orig_path)

    flash_t('flash_restore_success', 'success', filename=entry["filename"], folder=entry.get("original_folder", translate("flash_original_location")))
    log_action('restore', {'file': entry['filename'], 'to': entry.get('original_folder', '')})
    return redirect(url_for('trash_overview'))


@app.route('/trash/delete', methods=['POST'])
def trash_permanent_delete():
    """Permanently delete a file from trash"""
    trash_id = request.form.get('trash_id', '')

    entry = permanent_delete(trash_id)
    if not entry:
        flash_t('flash_trash_item_not_found', 'error')
        return redirect(url_for('trash_overview'))

    # Delete from pod _trash/ via filesystem
    rel_path = url_to_relative_path(entry['trash_url'])
    if rel_path:
        pod_delete(rel_path)

    flash_t('flash_permanent_delete', 'success', filename=entry["filename"])
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
    css_email = os.getenv('CSS_EMAIL', '')
    css_password_raw = os.getenv('CSS_PASSWORD', '')
    css_password_available = bool(css_password_raw) and not is_bcrypt_hash(css_password_raw)
    return render_template('profile.html',
        webid=OWNER_WEBID,
        pod_url=SOLID_POD_URL,
        stats=stats,
        bridge_url=bridge_url,
        bridge_configured=bool(bridge_password),
        css_email=css_email,
        css_password=css_password_raw if css_password_available else '',
        css_password_available=css_password_available,
    )


@app.route('/profile/bridge-password', methods=['POST'])
def change_bridge_password():
    if BRIDGE_MODE:
        abort(403)

    new_password = request.form.get('new_password', '').strip()

    if len(new_password) < 8:
        flash_t('flash_password_too_short', 'error')
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

    flash_t('flash_password_changed')
    log_action('bridge_password_changed', {})
    return redirect(url_for('profile'))


@app.route('/profile/css-password', methods=['POST'])
def change_css_password():
    if BRIDGE_MODE:
        abort(403)

    new_password = request.form.get('new_password', '').strip()
    if len(new_password) < 8:
        flash_t('flash_password_too_short', 'error')
        return redirect(url_for('profile'))

    email = os.getenv('CSS_EMAIL', '')
    current_password = os.getenv('CSS_PASSWORD', '')
    css_base = CSS_BASE_URL or 'http://127.0.0.1:3000'

    if not email or not current_password or is_bcrypt_hash(current_password):
        flash_t('flash_css_password_unavailable', 'error')
        return redirect(url_for('profile'))

    try:
        r = requests.get(f'{css_base}/.account/',
            headers={'Accept': 'application/json'}, timeout=10)
        if r.status_code != 200:
            flash_t('flash_css_unreachable', 'error')
            return redirect(url_for('profile'))

        initial_controls = r.json().get('controls', {})
        login_url = (
            initial_controls.get('password', {}).get('login')
            or initial_controls.get('html', {}).get('password', {}).get('login')
        )
        if not login_url:
            flash_t('flash_css_password_change_failed', 'error')
            return redirect(url_for('profile'))

        r = requests.post(login_url,
            json={'email': email, 'password': current_password, 'remember': False},
            timeout=10)
        if r.status_code not in (200, 201):
            flash_t('flash_css_password_change_failed', 'error')
            return redirect(url_for('profile'))

        authorization = r.json().get('authorization')
        if not authorization:
            flash_t('flash_css_password_change_failed', 'error')
            return redirect(url_for('profile'))

        r = requests.get(f'{css_base}/.account/',
            headers={
                'Authorization': f'CSS-Account-Token {authorization}',
                'Accept': 'application/json'
            }, timeout=10)
        if r.status_code != 200:
            flash_t('flash_css_password_change_failed', 'error')
            return redirect(url_for('profile'))

        full_controls = r.json().get('controls', {})
        password_section = full_controls.get('password', {})
        update_url = password_section.get('update')
        if not update_url:
            flash_t('flash_css_password_change_failed', 'error')
            return redirect(url_for('profile'))

        r = requests.post(update_url,
            headers={
                'Authorization': f'CSS-Account-Token {authorization}',
                'Content-Type': 'application/json',
            },
            json={'oldPassword': current_password, 'newPassword': new_password},
            timeout=10)
        if r.status_code not in (200, 201, 204):
            flash_t('flash_css_password_change_failed', 'error')
            return redirect(url_for('profile'))

    except requests.RequestException:
        flash_t('flash_css_unreachable', 'error')
        return redirect(url_for('profile'))

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

        found = False
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('CSS_PASSWORD='):
                    f.write(f'CSS_PASSWORD={new_password}\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f'CSS_PASSWORD={new_password}\n')

        load_dotenv(env_path, override=True)
        os.environ['CSS_PASSWORD'] = new_password

    flash_t('flash_css_password_changed')
    log_action('css_password_changed', {})
    return redirect(url_for('profile'))


@app.route('/settings')
def settings():
    """Show settings page"""
    ai_provider = os.environ.get('AI_PROVIDER', 'local')
    api_key_raw = os.environ.get('ANTHROPIC_API_KEY', '')
    api_key_masked = f'****{api_key_raw[-4:]}' if len(api_key_raw) >= 4 else ''

    return render_template('settings.html',
                           watermark_enabled=is_watermark_enabled(),
                           crash_reporting_enabled=is_crash_reporting_enabled(),
                           ai_provider=ai_provider,
                           api_key_masked=api_key_masked,
                           api_key_set=bool(api_key_raw),
                           ocr_provider=os.environ.get('OCR_PROVIDER', 'local'),
                           mistral_key_set=bool(os.environ.get('MISTRAL_API_KEY', '')),
                           mistral_key_masked='****' + os.environ.get('MISTRAL_API_KEY', '')[-4:] if os.environ.get('MISTRAL_API_KEY', '') else '')


def update_env(env_path, key, value):
    """Update of voeg een key-value paar toe in .env"""
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

    with open(env_path, 'w') as f:
        for line in lines:
            if line.startswith(f'{key}='):
                f.write(f'{key}={value}\n')
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f'{key}={value}\n')

    load_dotenv(env_path, override=True)


@app.route('/settings/watermark', methods=['POST'])
def toggle_watermark():
    """Toggle watermark setting in .env"""
    if BRIDGE_MODE:
        flash_t('flash_not_available_bridge', 'error')
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

    flash_t('flash_watermark_status', 'success', status=translate('flash_watermark_on') if enabled == 'true' else translate('flash_watermark_off'))
    return redirect(url_for('settings'))


@app.route('/settings/crash-reporting', methods=['POST'])
def toggle_crash_reporting():
    """Toggle anonymous crash reporting setting in .env"""
    if BRIDGE_MODE:
        flash_t('flash_not_available_bridge', 'error')
        return redirect(url_for('settings'))

    enabled = 'true' if request.form.get('enabled') == 'true' else 'false'
    env_path = os.path.join(PROJECT_DIR, '.env')

    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

        found = False
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith('CRASH_REPORTING='):
                    f.write(f'CRASH_REPORTING={enabled}\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f'CRASH_REPORTING={enabled}\n')
    else:
        with open(env_path, 'w') as f:
            f.write(f'CRASH_REPORTING={enabled}\n')

    os.environ['CRASH_REPORTING'] = enabled

    flash_t('flash_crash_status', 'success', status=translate('flash_watermark_on') if enabled == 'true' else translate('flash_watermark_off'))
    return redirect(url_for('settings'))


@app.route('/settings/ai-provider', methods=['POST'])
def change_ai_provider():
    """Wijzig AI-provider: lokaal (Ollama) of hybride (Claude API)"""
    if BRIDGE_MODE:
        abort(403)

    provider = request.form.get('ai_provider', 'local')
    api_key = request.form.get('anthropic_api_key', '').strip()

    if provider not in ('local', 'hybrid'):
        flash_t('flash_invalid_choice', 'error')
        return redirect(url_for('settings'))

    if provider == 'hybrid' and not api_key:
        # Check of er al een key in env staat
        existing_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not existing_key:
            flash_t('flash_api_key_required', 'error')
            return redirect(url_for('settings'))

    env_path = os.path.join(PROJECT_DIR, '.env')
    update_env(env_path, 'AI_PROVIDER', provider)
    if api_key:
        update_env(env_path, 'ANTHROPIC_API_KEY', api_key)

    # Herlaad in huidige process
    os.environ['AI_PROVIDER'] = provider
    if api_key:
        os.environ['ANTHROPIC_API_KEY'] = api_key

    # Update ai_service globals
    import ai_service
    ai_service.AI_PROVIDER = provider
    if api_key:
        ai_service.ANTHROPIC_API_KEY = api_key

    label = 'Lokaal (Ollama)' if provider == 'local' else 'Hybride (Claude API)'
    flash_t('flash_ai_provider_set', 'success', label=label)
    return redirect(url_for('settings'))


@app.route('/settings/ocr-provider', methods=['POST'])
def change_ocr_provider():
    """Wijzig OCR-provider: lokaal (Tesseract) of Mistral (EU cloud)"""
    if BRIDGE_MODE:
        abort(403)

    provider = request.form.get('ocr_provider', 'local')
    api_key = request.form.get('mistral_api_key', '').strip()

    if provider not in ('local', 'mistral'):
        flash_t('flash_invalid_choice', 'error')
        return redirect(url_for('settings'))

    if provider == 'mistral' and not api_key:
        existing_key = os.environ.get('MISTRAL_API_KEY', '')
        if not existing_key:
            flash_t('flash_mistral_key_required', 'error')
            return redirect(url_for('settings'))

    env_path = os.path.join(PROJECT_DIR, '.env')
    update_env(env_path, 'OCR_PROVIDER', provider)
    if api_key:
        update_env(env_path, 'MISTRAL_API_KEY', api_key)

    os.environ['OCR_PROVIDER'] = provider
    if api_key:
        os.environ['MISTRAL_API_KEY'] = api_key

    import ai_service
    ai_service.OCR_PROVIDER = provider
    if api_key:
        ai_service.MISTRAL_API_KEY = api_key

    label = 'Lokaal (Tesseract)' if provider == 'local' else 'Mistral OCR (EU)'
    flash_t('flash_ocr_provider_set', 'success', label=label)
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
        flash_t('flash_backup_failed', 'error', error=str(e))
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
            flash_t('flash_folder_init_failed', 'error', folder=folder)

    if welcome and created:
        flash_t('flash_vault_ready')
    else:
        if created:
            flash(f'{len(created)} mappen aangemaakt: {", ".join(created)}', 'success')
        if skipped:
            flash(f'{len(skipped)} mappen bestonden al: {", ".join(skipped)}', 'success')
        if not created and not skipped:
            flash_t('flash_no_folders_created', 'error')

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
        flash_t('flash_not_available_bridge', 'error')
        return redirect(url_for('index'))

    folder_path = folder_path.strip('/')
    full_path = safe_pod_path(folder_path)
    if not full_path or not os.path.isdir(full_path):
        flash_t('flash_folder_not_found', 'error')
        return redirect(url_for('index'))

    folder_name = folder_path.split('/')[-1] if '/' in folder_path else folder_path

    if request.method == 'POST':
        rule = request.form.get('rule', 'owner')
        policy = build_policy(folder_name, rule)
        policy_file = os.path.join(full_path, '.policy.jsonld')
        with open(policy_file, 'w', encoding='utf-8') as f:
            _json.dump(policy, f, indent=4, ensure_ascii=False)
        flash_t('flash_policy_updated', 'success', name=folder_name)
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


# === INTENTIEPOLICY: ODRL-Offer per intentie (MyTerms-demo, subtaak 3) ===
# Los van build_policy(): de mapregels hierboven blijven ongemoeid. Vorm en namen staan
# in ontwikkeling/mysolido_notitie_datamodel-myterms_20-09-2026.md (§3). Eén Offer per intentie,
# bestand intenties/<uuid>.policy.jsonld, uid urn:mysolido:policy:intention:<uuid>.
# De constanten PROFILE_ATTRIBUTES en INTENTION_PURPOSES staan verderop in dit bestand;
# de functies hier gebruiken ze alleen op het moment van aanroepen.

INTENTION_POLICY_CONTEXT = [
    "http://www.w3.org/ns/odrl.jsonld",
    {"dpv": "https://w3id.org/dpv#", "rdfs": "http://www.w3.org/2000/01/rdf-schema#"}
]
INTENTION_POLICY_UID_PREFIX = 'urn:mysolido:policy:intention:'
PARTY_URN_PREFIX = 'urn:mysolido:party:'
OPEN_OFFER_WHO_NL = 'Iedereen die deze voorwaarden accepteert'


def intention_policy_uid(intention_id):
    return f'{INTENTION_POLICY_UID_PREFIX}{intention_id}'


def intention_policy_relpath(intention_id):
    return f'intenties/{intention_id}.policy.jsonld'


def intention_id_from_record(record):
    return str(record.get('@id', '')).rsplit(':', 1)[-1]


def generate_party_id():
    """Partij-id in dezelfde vorm als consent_new(): urn:mysolido:party:<hex>."""
    return f'{PARTY_URN_PREFIX}{secrets.token_hex(4)}'


def build_intention_policy(record):
    """ODRL-Offer voor een mysolido:Intention met sharedAttributes (zie notitie §3)."""
    intention_id = intention_id_from_record(record)
    targets = [a['@id'] for a in record.get('mysolido:sharedAttributes', []) if a.get('@id')]
    purpose_id = (record.get('mysolido:purpose') or {}).get(
        '@id', f'urn:mysolido:purpose:{DEFAULT_INTENTION_PURPOSE}')

    permission = {"target": targets}
    assignee = None
    if record.get('mysolido:offerMode') == 'targeted':
        party = record.get('mysolido:targetedParty') or {}
        assignee = {"@id": party.get('@id', ''), "rdfs:label": party.get('name', '')}
        permission["assignee"] = assignee
    permission["action"] = "use"
    permission["constraint"] = [
        {"leftOperand": "purpose", "operator": "eq", "rightOperand": {"@id": purpose_id}},
        {"leftOperand": "dateTime", "operator": "lteq",
         "rightOperand": {"@type": "xsd:dateTime", "@value": record.get('schema:validThrough', '')}},
    ]

    policy = {
        "@context": list(INTENTION_POLICY_CONTEXT),
        "@type": "Offer",
        "uid": intention_policy_uid(intention_id),
        "profile": "http://www.w3.org/ns/odrl/2/core",
        "assigner": os.getenv('WEBID', WEBID),
        "permission": [permission],
    }
    if record.get('mysolido:noOnwardTransfer'):
        prohibition = {"target": list(targets)}
        if assignee:
            prohibition["assignee"] = dict(assignee)
        prohibition["action"] = ["distribute", "transfer"]
        policy["prohibition"] = [prohibition]
    return policy


def write_intention_policy(record):
    """Schrijf de Offer naast het intentierecord. Geeft de policy terug, of None zonder targets."""
    if not record.get('mysolido:sharedAttributes'):
        return None
    policy = build_intention_policy(record)
    pod_write(intention_policy_relpath(intention_id_from_record(record)),
              _json.dumps(policy, indent=2, ensure_ascii=False))
    return policy


def load_intention_policy(intention_id):
    """Lees intenties/<uuid>.policy.jsonld; None als het bestand ontbreekt of onleesbaar is."""
    path = safe_pod_path(intention_policy_relpath(intention_id))
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return _json.load(f)
    except (ValueError, IOError):
        return None


def format_date_nl_iso(value):
    """'2026-10-04T08:56:20+00:00' -> '04-10-2026'; onbekende invoer komt ongewijzigd terug."""
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime('%d-%m-%Y')
    except (TypeError, ValueError):
        return value or ''


@app.template_filter('nl_date')
def nl_date_filter(value):
    """Jinja-filter: ISO-datum/tijd -> dd-mm-jjjj (demo-pagina's, subtaak 5)."""
    return format_date_nl_iso(value)


def _amsterdam_offset(dt_utc):
    """Terugval zonder tijdzonedatabase: CET (+1) of CEST (+2) volgens de EU-regel
    (zomertijd van de laatste zondag van maart 01:00 UTC tot de laatste zondag van oktober 01:00 UTC)."""
    def last_sunday(year, month):
        d = datetime(year, month, 31 if month in (3, 10) else 30, 1, 0, tzinfo=timezone.utc)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    summer = last_sunday(dt_utc.year, 3) <= dt_utc < last_sunday(dt_utc.year, 10)
    return timedelta(hours=2 if summer else 1)


def format_datetime_nl(value):
    """ISO-tijdstip -> 'dd-mm-jjjj HH:MM' in Nederlandse tijd (Europe/Amsterdam).

    Records in de Pod blijven in UTC (+00:00); alleen de weergave rekent om. Een tijdstip zonder
    tijdzone (zoals last_sync van de Bridge-sync, dat al lokale tijd is) wordt niet verschoven.
    Onbekende invoer komt ongewijzigd terug.
    """
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return value or ''
    if dt.tzinfo is not None:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.astimezone(ZoneInfo('Europe/Amsterdam'))
        except Exception:   # geen tijdzonedatabase op dit systeem
            dt_utc = dt.astimezone(timezone.utc)
            dt = dt_utc + _amsterdam_offset(dt_utc)
    return dt.strftime('%d-%m-%Y %H:%M')


@app.template_filter('nl_datetime')
def nl_datetime_filter(value):
    """Jinja-filter: ISO-tijdstip -> dd-mm-jjjj HH:MM in Nederlandse tijd (21-09-2026)."""
    return format_datetime_nl(value)


def _join_nl(items):
    items = [i for i in items if i]
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + ' en ' + items[-1]


def _lower_first(text):
    return text[:1].lower() + text[1:] if text else ''


def _summary_label(label):
    """Label voor in de zin: kleine beginletter, zonder toelichting tussen haakjes ("(4 cijfers)")."""
    return _lower_first(re.sub(r'\s*\([^)]*\)\s*$', '', label or ''))


def _operand_value(operand, key):
    return operand.get(key, '') if isinstance(operand, dict) else ''


def intention_policy_summary_nl(policy, record):
    """Nederlandse zin voor een intentie-Offer; los van policy_summary_nl() (mapregels).

    Vorm: "<Wie> mag <labels> gebruiken, uitsluitend voor <doel>, tot <dd-mm-jjjj>,
    en mag ze niet doorleveren." Zonder prohibition vervalt het laatste zinsdeel.
    """
    if not policy:
        return ''
    perm = (policy.get('permission') or [{}])[0]
    targets = perm.get('target', [])
    if isinstance(targets, str):
        targets = [targets]
    labels = []
    for urn in targets:
        key = urn[len(ATTRIBUTE_URN_PREFIX):] if str(urn).startswith(ATTRIBUTE_URN_PREFIX) else None
        attr = PROFILE_ATTRIBUTES.get(key) if key else None
        labels.append(_summary_label(attr['label']) if attr else str(urn))

    purpose_label = (record.get('mysolido:purpose') or {}).get('label', '')
    until = ''
    for constraint in perm.get('constraint', []):
        if constraint.get('leftOperand') == 'purpose':
            code = str(_operand_value(constraint.get('rightOperand'), '@id')).rsplit(':', 1)[-1]
            if code in INTENTION_PURPOSES:
                purpose_label = INTENTION_PURPOSES[code]['label']
        elif constraint.get('leftOperand') == 'dateTime':
            until = format_date_nl_iso(_operand_value(constraint.get('rightOperand'), '@value'))

    assignee = perm.get('assignee')
    if isinstance(assignee, dict) and assignee.get('rdfs:label'):
        who = assignee['rdfs:label']
    elif assignee:
        who = (record.get('mysolido:targetedParty') or {}).get('name') or str(assignee)
    else:
        who = OPEN_OFFER_WHO_NL

    sentence = f"{who} mag {_join_nl(labels)} gebruiken, uitsluitend voor {_lower_first(purpose_label)}"
    if until:
        sentence += f", tot {until}"
    if policy.get('prohibition'):
        sentence += ", en mag ze niet doorleveren"
    return sentence + '.'


# === ACCEPTATIE EN AGREEMENT (MyTerms-demo, subtaak 4a) ===
# De wederpartij accepteert de Offer van een actieve intentie via /verzoek/intentie/<uuid>.
# conclude_agreement() is het sluitmoment: bij offerMode open direct bij acceptatie, bij
# targeted pas na bevestiging door de eigenaar in verzoek_approve(). Eén functie, twee
# aanroepplekken. Vorm en namen: ontwikkeling/mysolido_notitie_datamodel-myterms_20-09-2026.md (§3).
# In 4b komt het consentrecord als één toevoeging in conclude_agreement().

AGREEMENT_UID_PREFIX = 'urn:mysolido:agreement:'
REQUEST_STATUS_ACCEPTED = 'geaccepteerd'
REQUEST_STATUS_AWAITING = 'wacht-op-bevestiging'
REQUEST_STATUSES_WITH_RESPONSE = ('goedgekeurd', REQUEST_STATUS_ACCEPTED)
REQUEST_STATUS_WITHDRAWN = 'ingetrokken'   # toestemming ingetrokken (subtaak 4b)


def agreement_uid(request_id):
    return f'{AGREEMENT_UID_PREFIX}{request_id}'


def agreement_relpath(request_id):
    return f'verzoeken/{request_id}.agreement.jsonld'


def request_response_relpath(request_id):
    return f'verzoeken/{request_id}_response.json'


def utc_now_iso_seconds():
    """ISO-8601 UTC zonder microseconden, bijv. 2026-09-20T12:34:56+00:00."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_of_pod_file(relative_path):
    """'sha256:<hex>' van een bestand in de Pod, of None als het ontbreekt."""
    path = safe_pod_path(relative_path)
    if not path or not os.path.isfile(path):
        return None
    import hashlib
    with open(path, 'rb') as f:
        return 'sha256:' + hashlib.sha256(f.read()).hexdigest()


def save_pod_json(relative_path, data):
    """Schrijf een record als JSON (indent 2) via pod_write; '_'-sleutels worden weggelaten."""
    clean = {k: v for k, v in data.items() if not str(k).startswith('_')}
    return pod_write(relative_path, _json.dumps(clean, indent=2, ensure_ascii=False))


def load_pod_json(relative_path):
    """Lees een JSON-bestand uit de Pod; None als het ontbreekt of onleesbaar is."""
    path = safe_pod_path(relative_path)
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return _json.load(f)
    except (ValueError, IOError):
        return None


def load_intention_record(intention_id):
    return load_pod_json(f'intenties/{intention_id}.jsonld')


def load_request_record(request_id):
    return load_pod_json(f'verzoeken/{request_id}.jsonld')


def load_agreement(request_id):
    return load_pod_json(agreement_relpath(request_id))


def attribute_label_from_urn(urn):
    key = str(urn)[len(ATTRIBUTE_URN_PREFIX):] if str(urn).startswith(ATTRIBUTE_URN_PREFIX) else None
    attr = PROFILE_ATTRIBUTES.get(key) if key else None
    return attr['label'] if attr else str(urn)


def _rule_with_assignee(rule, assignee):
    """Kopie van een ODRL-regel met de partij als assignee (target, assignee, rest)."""
    out = {}
    if 'target' in rule:
        out['target'] = _json.loads(_json.dumps(rule['target']))
    out['assignee'] = dict(assignee)
    for key, value in rule.items():
        if key in ('target', 'assignee'):
            continue
        out[key] = _json.loads(_json.dumps(value))
    return out


def build_agreement(offer, request_record, party):
    """odrl:Agreement: de Offer letterlijk gekopieerd, met de partij als assignee op elke regel."""
    request_id = str(request_record.get('@id', '')).rsplit(':', 1)[-1]
    assignee = {"@id": party.get('@id', ''), "rdfs:label": party.get('rdfs:label', '')}
    agreement = {
        "@context": list(INTENTION_POLICY_CONTEXT),
        "@type": "Agreement",
        "uid": agreement_uid(request_id),
        "profile": "http://www.w3.org/ns/odrl/2/core",
        "assigner": os.getenv('WEBID', WEBID),
        "permission": [_rule_with_assignee(p, assignee) for p in offer.get('permission', [])],
    }
    if offer.get('prohibition'):
        agreement["prohibition"] = [_rule_with_assignee(p, assignee) for p in offer['prohibition']]
    agreement["mysolido:offer"] = offer.get('uid', '')
    agreement["mysolido:request"] = request_record.get('@id', '')
    agreement["mysolido:acceptedAt"] = request_record.get('mysolido:acceptedAt', '')
    agreement["mysolido:offerHash"] = request_record.get('mysolido:acceptedPolicyHash', '')
    return agreement


def build_response_data(intention_record, agreement):
    """Inhoud van <uuid>_response.json: uitsluitend de sharedAttributes van de intentie."""
    return {
        "mysolido:intention": intention_record.get('@id', ''),
        "mysolido:agreement": agreement.get('uid', ''),
        "mysolido:validUntil": intention_record.get('schema:validThrough', ''),
        "attributes": [
            {"@id": a.get('@id', ''), "label": a.get('label', ''), "valueLabel": a.get('valueLabel', '')}
            for a in intention_record.get('mysolido:sharedAttributes', [])
        ],
    }


CONSENT_RECORD_CONTEXT = {
    "dpv": "https://w3id.org/dpv#",
    "pd": "https://w3id.org/dpv/pd#",
    "loc": "https://w3id.org/dpv/loc#",
    "eu-gdpr": "https://w3id.org/dpv/legal/eu/gdpr#",
    "dct": "http://purl.org/dc/terms/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "mysolido": "https://mysolido.com/vocab#"
}
CONSENT_RECORD_SCHEMA = "ISO/IEC TS 27560:2023"
CONSENT_RECORD_SCHEMA_VERSION = "1.0"


def build_consent_record(request_record, intention_record, agreement):
    """Consentrecord in de structuur van ISO/IEC TS 27560 met DPV-vocabulaire (subtaak 4b).

    Velden en termen: notitie §3, rij Consentrecord. Geverifieerd tegen de DPV-27560-gids en
    DPV 2.1; waar DPV geen term heeft staat mysolido:<veld>. De attribuut-urn is de identiteit
    van elk gedeeld gegeven, de pd-term uit PROFILE_ATTRIBUTES de categorie erbij.
    """
    consent_id = generate_consent_id()
    now = utc_now_iso_seconds()
    webid = os.getenv('WEBID', WEBID)
    party = request_record.get('mysolido:party') or {}
    purpose = intention_record.get('mysolido:purpose') or {}
    accepted_at = request_record.get('mysolido:acceptedAt', now)
    # B4 (besluit 21-09-2026, optie A): de einddatum van het aanbod (schema:validThrough) is leidend.
    # De Agreement is een letterlijke kopie van de Offer en heeft geen eigen einddatum; het record
    # noemt alleen mysolido:validUntil. Het eerdere dpv:hasDuration (mysolido:days / iso8601, de
    # afgeronde duur vanaf acceptatie) is weggelaten: het suggereerde een tweede, afwijkende looptijd
    # ("14 dagen vanaf acceptatie"). Records van vóór 21-09 kunnen het nog bevatten; lezers negeren het.
    valid_until = intention_record.get('schema:validThrough', '')
    prohibited = bool(intention_record.get('mysolido:noOnwardTransfer'))

    personal_data = []
    for attr in intention_record.get('mysolido:sharedAttributes', []):
        key = str(attr.get('@id', ''))[len(ATTRIBUTE_URN_PREFIX):]
        meta = PROFILE_ATTRIBUTES.get(key, {})
        personal_data.append({
            "@id": attr.get('@id', ''),
            "@type": meta.get('dpv', f'mysolido:{key}'),
            "rdfs:label": attr.get('label', ''),
            "mysolido:value": attr.get('valueLabel', ''),
        })

    record = {
        "@context": dict(CONSENT_RECORD_CONTEXT),
        "@type": "dpv:ConsentRecord",
        "@id": f"urn:mysolido:consent:{consent_id}",
        # --- kop (27560: schema_version, record_id, pii_principal_id) ---
        "dct:conformsTo": CONSENT_RECORD_SCHEMA,
        "mysolido:recordSchemaVersion": CONSENT_RECORD_SCHEMA_VERSION,
        "dct:identifier": consent_id,
        "dct:title": f"{intention_record.get('mysolido:categoryLabel', 'Intentie')} — {party.get('rdfs:label', '')}",
        "dct:description": intention_policy_summary_nl(agreement, intention_record),
        "dct:created": now,
        "dct:modified": now,
        "dpv:hasDataSubject": {"@id": webid, "@type": "dpv:DataSubject"},
        # --- verwerking (purpose, lawful_basis, pii_information, pii_controllers, retention, recipients, jurisdiction) ---
        "dpv:hasPurpose": {
            "@id": purpose.get('@id', ''),
            "@type": purpose.get('dpv', 'dpv:Purpose'),
            "rdfs:label": purpose.get('label', ''),
        },
        "dpv:hasLegalBasis": "dpv:ExplicitlyExpressedConsent",
        "dpv:hasPersonalData": personal_data,
        "dpv:hasDataController": {
            "@id": party.get('@id', ''),
            "@type": "dpv:DataController",
            "rdfs:label": party.get('rdfs:label', ''),
            "dct:title": party.get('rdfs:label', ''),
            "mysolido:contactName": party.get('mysolido:contactName', ''),
            "mysolido:contact": party.get('mysolido:contact', ''),
        },
        "dpv:hasStorageCondition": {
            "@type": "dpv:StorageDuration",
            "mysolido:validUntil": valid_until,   # = schema:validThrough van de intentie (B4)
        },
        "dpv:hasRecipient": [],
        "mysolido:onwardTransfer": "prohibited" if prohibited else "permitted",
        "dpv:hasJurisdiction": {"@id": "loc:NL"},
        # --- gebeurtenis (event_state, event_time, entity_id; event_type via hasLegalBasis) ---
        "dpv:hasConsentStatus": CONSENT_STATUS_GIVEN,
        "mysolido:events": [
            {"@type": "given", "at": accepted_at, "by": party.get('@id', '')},
        ],
        "dpv:isImplementedByEntity": {"@id": webid},
        # --- koppelingen en rechten ---
        "mysolido:agreement": agreement.get('uid', ''),
        "mysolido:intention": intention_record.get('@id', ''),
        "mysolido:request": request_record.get('@id', ''),
        "mysolido:acceptedPolicy": request_record.get('mysolido:acceptedPolicy', ''),
        "mysolido:offerHash": request_record.get('mysolido:acceptedPolicyHash', ''),
        "mysolido:intentionCategoryLabel": intention_record.get('mysolido:categoryLabel', ''),
        "dpv:hasRight": "eu-gdpr:A7-3",
    }
    if prohibited:
        record["mysolido:onwardTransferProhibition"] = agreement.get('uid', '')
    return record


def write_consent_record(record):
    """Schrijf een consentrecord in toestemmingen/ (zelfde bestandsnaam als consent_new)."""
    consent_id = record.get('dct:identifier') or str(record.get('@id', '')).rsplit(':', 1)[-1]
    pod_mkdir('toestemmingen')
    pod_write(f'toestemmingen/{consent_id}.jsonld', _json.dumps(record, indent=2, ensure_ascii=False))
    return consent_id


def conclude_agreement(request_record, intention_record):
    """Sluitmoment: Agreement en response schrijven, verzoek en intentie bijwerken.

    Verwacht een verzoekrecord met mysolido:party, acceptedPolicy, acceptedAt en
    acceptedPolicyHash, en een intentierecord met een bestaande Offer. Schrijft beide
    records terug en geeft de Agreement terug.
    """
    request_id = str(request_record.get('@id', '')).rsplit(':', 1)[-1]
    intention_id = intention_id_from_record(intention_record)
    offer = load_intention_policy(intention_id) or build_intention_policy(intention_record)
    party = request_record.get('mysolido:party') or {}

    agreement = build_agreement(offer, request_record, party)
    save_pod_json(agreement_relpath(request_id), agreement)

    response_data = build_response_data(intention_record, agreement)
    save_pod_json(request_response_relpath(request_id), response_data)

    request_record['mysolido:status'] = REQUEST_STATUS_ACCEPTED
    request_record['mysolido:agreement'] = agreement['uid']
    request_record['mysolido:approvedData'] = [a['@id'] for a in response_data['attributes']]
    request_record['mysolido:responseLink'] = f"/verzoek/response/{request_record.get('mysolido:statusToken', '')}"
    request_record['mysolido:validUntil'] = intention_record.get('schema:validThrough', '')

    # Consentrecord (subtaak 4b): één record per gesloten Agreement, ISO/IEC TS 27560-structuur
    consent_record = build_consent_record(request_record, intention_record, agreement)
    consent_id = write_consent_record(consent_record)
    request_record['mysolido:consent'] = consent_record['@id']
    save_pod_json(f'verzoeken/{request_id}.jsonld', request_record)

    accepted_by = intention_record.setdefault('mysolido:acceptedBy', [])
    if request_record.get('@id') not in accepted_by:
        accepted_by.append(request_record.get('@id'))
    save_pod_json(f'intenties/{intention_id}.jsonld', intention_record)

    log_action('request_accept', {'id': request_id, 'intention': intention_id,
                                  'party': party.get('@id', ''), 'policy': offer.get('uid', '')})
    log_action('agreement_create', {'id': request_id, 'agreement': agreement['uid'],
                                    'offer_hash': request_record.get('mysolido:acceptedPolicyHash', '')})
    log_action('consent_create', {'id': consent_id, 'agreement': agreement['uid'],
                                  'controller': party.get('@id', ''), 'title': consent_record.get('dct:title', '')})
    return agreement


def accepted_requests_for(intention_record):
    """Weergavelijst voor 'Geaccepteerd door' op de intentiepagina."""
    items = []
    for request_uri in intention_record.get('mysolido:acceptedBy', []) or []:
        request_id = str(request_uri).rsplit(':', 1)[-1]
        record = load_request_record(request_id) or {}
        party = record.get('mysolido:party') or {}
        items.append({
            'request_id': request_id,
            'party': party.get('rdfs:label') or record.get('mysolido:requester', {}).get('schema:name', '?'),
            'contact_name': party.get('mysolido:contactName', ''),
            'organisation': party.get('mysolido:organisation', ''),
            'accepted_at': format_date_nl_iso(record.get('mysolido:acceptedAt', '')),
            'agreement': record.get('mysolido:agreement', ''),
            'consent': record.get('mysolido:consent', ''),
            'status': record.get('mysolido:status', ''),
            'withdrawn': record.get('mysolido:status') == REQUEST_STATUS_WITHDRAWN,   # toestemming ingetrokken (4b)
            'withdrawn_at': format_date_nl_iso(record.get('mysolido:withdrawnAt', '')),
        })
    return items


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
                # oude statuswaarden alleen in het geheugen normaliseren (geen migratie op schijf)
                if 'dpv:hasConsentStatus' in record:
                    record['dpv:hasConsentStatus'] = normalize_consent_status(record['dpv:hasConsentStatus'])
                consents.append(record)
            except (_json.JSONDecodeError, IOError):
                continue

    consents.sort(key=lambda r: r.get('dct:created', ''), reverse=True)
    return consents


# Statustermen (subtaak 4b): DPV kent dpv:ConsentGiven / dpv:ConsentWithdrawn / dpv:ConsentExpired.
# De waarden dpv:ConsentStatusGiven / dpv:ConsentStatusWithdrawn die tot 20-09-2026 werden
# geschreven bestaan niet in DPV; bij lezen worden ze genormaliseerd, op schijf blijven ze staan.
CONSENT_STATUS_GIVEN = 'dpv:ConsentGiven'
CONSENT_STATUS_WITHDRAWN = 'dpv:ConsentWithdrawn'
CONSENT_STATUS_EXPIRED = 'dpv:ConsentExpired'
_LEGACY_CONSENT_STATUS = {
    'dpv:ConsentStatusGiven': CONSENT_STATUS_GIVEN,
    'dpv:ConsentStatusWithdrawn': CONSENT_STATUS_WITHDRAWN,
}


def normalize_consent_status(value):
    """Oude statuswaarden naar de DPV-termen; onbekende waarden ongewijzigd."""
    return _LEGACY_CONSENT_STATUS.get(value, value)


def consent_expiry_time(record):
    """Einddatum van een consentrecord: 27560-vorm (hasStorageCondition.mysolido:validUntil)
    of de oude vorm (hasExpiry.hasExpiryTime). Leeg als er geen einddatum is."""
    storage = record.get('dpv:hasStorageCondition')
    if isinstance(storage, dict) and storage.get('mysolido:validUntil'):
        return str(storage['mysolido:validUntil'])
    expiry = record.get('dpv:hasExpiry', {})
    return str(expiry.get('dpv:hasExpiryTime', '')) if isinstance(expiry, dict) else ''


def consent_is_expired(record):
    expiry_time = consent_expiry_time(record)
    if not expiry_time:
        return False
    try:
        exp_dt = datetime.fromisoformat(expiry_time.replace('Z', '+00:00'))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        return exp_dt < datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


def get_consent_status_display(record):
    """Return status display info for a consent record (label, icon, class, DPV-term)"""
    status = normalize_consent_status(record.get('dpv:hasConsentStatus', ''))
    if status == CONSENT_STATUS_WITHDRAWN:
        return {'label': 'Ingetrokken', 'icon': '\u274c', 'class': 'status-withdrawn', 'term': CONSENT_STATUS_WITHDRAWN}

    if consent_is_expired(record):
        # "verlopen" wordt niet geschreven maar bij lezen afgeleid
        return {'label': 'Verlopen', 'icon': '\u23f0', 'class': 'status-expired', 'term': CONSENT_STATUS_EXPIRED}

    if status == CONSENT_STATUS_GIVEN:
        return {'label': 'Actief', 'icon': '\u2705', 'class': 'status-active', 'term': CONSENT_STATUS_GIVEN}

    return {'label': 'Onbekend', 'icon': '\u2753', 'class': 'status-unknown', 'term': status}


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
    date_str = datetime.now(timezone.utc).strftime('%Y%m%d')   # tijdzonebewust (subtaak 5)
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
        if isinstance(controller, dict):
            c['_receiver'] = controller.get('rdfs:label') or controller.get('dct:title', 'Onbekend')
        else:
            c['_receiver'] = str(controller)
        purpose = c.get('dpv:hasPurpose', {})
        if isinstance(purpose, dict):
            c['_purpose'] = purpose.get('rdfs:label') or purpose.get('dct:description', purpose.get('@type', 'Onbekend'))
        else:
            c['_purpose'] = str(purpose)
        c['_expiry_date'] = format_date_nl_iso(consent_expiry_time(c)) if consent_expiry_time(c) else ''
        c['_created_date'] = format_date_nl_iso(c.get('dct:created', ''))   # dd-mm-jjjj (subtaak 5)
        c['_category'] = c.get('mysolido:intentionCategoryLabel', '')   # intentiegebonden record (4b)
        enriched.append(c)

    return render_template('consent_list.html', consents=enriched)


@app.route('/consent/new', methods=['GET', 'POST'])
def consent_new():
    """Create a new consent record"""
    if BRIDGE_MODE:
        flash_t('flash_not_available_bridge', 'error')
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
            flash_t('flash_title_receiver_required', 'error')
            return redirect(url_for('consent_new'))

        consent_id = generate_consent_id()
        now = utc_now_iso_seconds()   # was datetime.utcnow() met Z-notatie (subtaak 5)
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
            "dpv:hasConsentStatus": CONSENT_STATUS_GIVEN,
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
            flash_t('flash_consent_saved', 'success', title=title)
            log_action('consent_create', {'title': title, 'receiver': receiver})
        else:
            flash_t('flash_consent_folder_not_found', 'error')

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
        flash_t('flash_consent_folder_not_found', 'error')
        return redirect(url_for('consent_list'))

    fpath = os.path.join(consent_dir, f"{consent_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_consent_not_found', 'error')
        return redirect(url_for('consent_list'))

    with open(fpath, 'r', encoding='utf-8') as f:
        raw_json = f.read()
    record = _json.loads(raw_json)

    # Regel (B6, 21-09-2026): opgeslagen records bevatten nooit weergave-informatie. De sleutels met
    # een underscore (_id, _status) bestaan alleen in het geheugen voor de template; de ruwe weergave
    # toont raw_json, het bestand zoals het in de Pod staat.
    record['_id'] = consent_id
    if 'dpv:hasConsentStatus' in record:
        record['dpv:hasConsentStatus'] = normalize_consent_status(record['dpv:hasConsentStatus'])
    record['_status'] = get_consent_status_display(record)

    # 27560-record (subtaak 4b): koppelingen als links, attributen met waarden, gebeurtenissen
    links = None
    if record.get('dct:conformsTo'):
        request_id = str(record.get('mysolido:request', '')).rsplit(':', 1)[-1]
        links = {
            'intention_id': str(record.get('mysolido:intention', '')).rsplit(':', 1)[-1],
            'request_id': request_id,
            'agreement_exists': bool(request_id) and pod_exists(agreement_relpath(request_id)),
        }

    return render_template('consent_detail.html',
        consent=record,
        raw_json=raw_json,
        links=links,
        expiry_date=format_date_nl_iso(consent_expiry_time(record)),
    )


@app.route('/consent/<consent_id>/withdraw', methods=['POST'])
def consent_withdraw(consent_id):
    """Withdraw a consent record"""
    if BRIDGE_MODE:
        flash_t('flash_not_available_bridge', 'error')
        return redirect(url_for('consent_list'))

    consent_dir = get_consent_dir()
    if not consent_dir:
        flash_t('flash_consent_folder_not_found', 'error')
        return redirect(url_for('consent_list'))

    fpath = os.path.join(consent_dir, f"{consent_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_consent_not_found', 'error')
        return redirect(url_for('consent_list'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    # "Toestemming intrekken" (subtaak 4b): status, gebeurtenis, modified; bij een
    # intentiegebonden record ook het verzoek op 'ingetrokken' zodat de responspagina sluit.
    # De Agreement blijft ongewijzigd als bewijs; dit record is de bron van de status.
    withdrawn_at = utc_now_iso_seconds()
    record['dpv:hasConsentStatus'] = CONSENT_STATUS_WITHDRAWN
    record['dct:modified'] = withdrawn_at
    if 'mysolido:events' in record or record.get('dct:conformsTo'):
        record.setdefault('mysolido:events', []).append(
            {"@type": "withdrawn", "at": withdrawn_at, "by": os.getenv('WEBID', WEBID)})

    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=4, ensure_ascii=False)

    linked_request = str(record.get('mysolido:request', '')).rsplit(':', 1)[-1]
    if linked_request:
        request_record = load_request_record(linked_request)
        if request_record:
            request_record['mysolido:status'] = REQUEST_STATUS_WITHDRAWN
            request_record['mysolido:withdrawnAt'] = withdrawn_at
            save_pod_json(f'verzoeken/{linked_request}.jsonld', request_record)

    title = record.get('dct:title', consent_id)
    flash_t('flash_consent_withdrawn', 'success', title=title)
    log_action('consent_withdraw', {'id': consent_id, 'title': title, 'request': linked_request or None})
    return redirect(url_for('consent_list'))


@app.route('/consent/<consent_id>/delete', methods=['POST'])
def consent_delete(consent_id):
    """Delete a consent record"""
    if BRIDGE_MODE:
        flash_t('flash_not_available_bridge', 'error')
        return redirect(url_for('consent_list'))

    consent_dir = get_consent_dir()
    if not consent_dir:
        flash_t('flash_consent_folder_not_found', 'error')
        return redirect(url_for('consent_list'))

    fpath = os.path.join(consent_dir, f"{consent_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_consent_not_found', 'error')
        return redirect(url_for('consent_list'))

    # B5 (besluit 21-09-2026, optie A): een record met mysolido:agreement is bewijs van een
    # gesloten afspraak en kan alleen worden ingetrokken, niet verwijderd (zoals bij de intentie).
    # Handmatige toestemmingen zonder Agreement blijven verwijderbaar.
    with open(fpath, 'r', encoding='utf-8') as f:
        existing = _json.load(f)
    if existing.get('mysolido:agreement'):
        flash_t('flash_consent_has_agreement', 'error')
        return redirect(url_for('consent_detail', consent_id=consent_id))

    os.remove(fpath)
    flash_t('flash_consent_deleted')
    log_action('consent_delete', {'id': consent_id})
    return redirect(url_for('consent_list'))


# === PROFILE DATA MODULE (Omgekeerde Google) ===


# === PROFIEL-ATTRIBUTEN (MyTerms-demo, subtaak 2) ===
# Eén bron van waarheid voor de deelbare profielvelden; zie
# ontwikkeling/mysolido_notitie_datamodel-myterms_20-09-2026.md (punt 1 en 2).
# Een nieuw attribuut is één regel in PROFILE_ATTRIBUTES: per-veldselectie in het
# intentieformulier en het snapshot in het intentierecord volgen daaruit. Alleen
# attributen met 'form_field' hebben een eigen invoerveld in profiel_data.html dat
# hier generiek wordt uitgelezen; de overige velden houden hun bestaande formulier-
# en opslagcode in profiel_data_save().
#   path : plaats van de waarde in profiel/profiel.jsonld (sleutels; een geheel
#          getal is een lijstindex)
#   dpv  : geverifieerde DPV-PD-term (DPV-PD 2.1), anders mysolido:<key>

PROFILE_CONTEXT = {
    "dpv": "https://w3id.org/dpv#",
    "pd": "https://w3id.org/dpv/pd#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "mysolido": "https://mysolido.com/vocab#"
}

PROFILE_GROUPS = {
    'personal':   {'label': 'Persoonlijk',   'icon': '\U0001f464'},
    'housing':    {'label': 'Woonsituatie',  'icon': '\U0001f3e0'},
    'household':  {'label': 'Gezin',         'icon': '\U0001f468‍\U0001f469‍\U0001f467‍\U0001f466'},
    'vehicle':    {'label': 'Voertuigen',    'icon': '\U0001f697'},
    'insurance':  {'label': 'Verzekeringen', 'icon': '\U0001f6e1️'},
    'occupation': {'label': 'Werk',          'icon': '\U0001f4bc'},
    'health':     {'label': 'Gezondheid',    'icon': '❤️'},
}

ATTRIBUTE_URN_PREFIX = 'urn:mysolido:attribute:'

PROFILE_ATTRIBUTES = {
    # -- personal --
    'age_category': {                                   # scenario-attribuut 1
        'label': 'Leeftijdscategorie', 'group': 'personal', 'input': 'select',
        'options': [('18-24', '18-24'), ('25-34', '25-34'), ('35-44', '35-44'),
                    ('45-54', '45-54'), ('55-64', '55-64'), ('65+', '65+')],
        'dpv': 'pd:AgeRange', 'path': ['pd:AgeRange'], 'form_field': 'age_category',
    },
    # -- housing --
    'housing_ownership': {
        'label': 'Eigendom', 'group': 'housing', 'input': 'select',
        'options': [('huur', 'Huur'), ('koop', 'Koop'), ('anders', 'Anders')],
        'dpv': 'mysolido:housing_ownership', 'path': ['pd:HousingOwnership'],
    },
    'housing_type': {
        'label': 'Woningtype', 'group': 'housing', 'input': 'select',
        'options': [('appartement', 'Appartement'), ('tussenwoning', 'Tussenwoning'),
                    ('hoekwoning', 'Hoekwoning'), ('vrijstaand', 'Vrijstaand'), ('anders', 'Anders')],
        'dpv': 'mysolido:housing_type', 'path': ['mysolido:housingType'],
    },
    'region': {
        'label': 'Regio / provincie', 'group': 'housing', 'input': 'text',
        'dpv': 'pd:Location', 'path': ['pd:Location'],
    },
    'postal_area': {                                    # scenario-attribuut 2
        'label': 'Postcodegebied (4 cijfers)', 'group': 'housing', 'input': 'text',
        'pattern': r'^\d{4}$', 'dpv': 'pd:PostalCode', 'path': ['pd:PostalCode'],
        'form_field': 'postal_area',
    },
    # -- household --
    'household_size': {
        'label': 'Aantal personen in huishouden', 'group': 'household', 'input': 'int',
        'dpv': 'mysolido:household_size', 'path': ['pd:HouseholdSize'],
    },
    'children': {
        'label': 'Kinderen (leeftijdscategorie)', 'group': 'household', 'input': 'list',
        'dpv': 'pd:FamilyStructure', 'path': ['pd:FamilyStructure', 'children'], 'item_keys': ['ageCategory'],
    },
    # -- vehicle --
    'vehicle_type': {                                   # scenario-attribuut 3 (bestaand veld)
        'label': 'Voertuigtype', 'group': 'vehicle', 'input': 'select',
        'options': [('auto', 'Auto'), ('motor', 'Motor'), ('scooter', 'Scooter'),
                    ('fiets', 'Fiets'), ('geen', 'Geen')],
        'dpv': 'pd:Vehicle', 'path': ['pd:Vehicle', 0, 'type'],
    },
    'vehicle_fuel': {
        'label': 'Brandstof', 'group': 'vehicle', 'input': 'select',
        'options': [('benzine', 'Benzine'), ('diesel', 'Diesel'), ('elektrisch', 'Elektrisch'),
                    ('hybride', 'Hybride'), ('nvt', 'N.v.t.')],
        'dpv': 'pd:Vehicle', 'path': ['pd:Vehicle', 0, 'fuel'],
    },
    'vehicle_year': {
        'label': 'Bouwjaar', 'group': 'vehicle', 'input': 'int',
        'dpv': 'pd:Vehicle', 'path': ['pd:Vehicle', 0, 'yearBuilt'],
    },
    # -- insurance --
    'insurances': {
        'label': 'Lopende verzekeringen', 'group': 'insurance', 'input': 'list',
        'dpv': 'pd:Insurance', 'path': ['pd:Insurance'], 'item_keys': ['type', 'provider'],
    },
    'claims_history': {                                 # scenario-attribuut 4
        'label': 'Schadeverleden', 'group': 'insurance', 'input': 'composite',
        'dpv': 'pd:Insurance',   # naaste bredere term; DPV-PD 2.1 kent geen claims-term
        'path': ['mysolido:claimsHistory'], 'form_field': True,
        'fields': {
            'claim_free_years': {'label': 'Schadevrije jaren', 'input': 'int', 'json_key': 'claimFreeYears'},
            'claims_last_3_years': {'label': 'Schade geclaimd in de laatste 3 jaar', 'input': 'bool',
                                    'json_key': 'claimsLast3Years'},
        },
    },
    # -- occupation --
    'work_sector': {
        'label': 'Sector', 'group': 'occupation', 'input': 'select',
        'options': [('ict', 'ICT'), ('zorg', 'Zorg'), ('onderwijs', 'Onderwijs'), ('bouw', 'Bouw'),
                    ('overheid', 'Overheid'), ('financieel', 'Financieel'), ('retail', 'Retail'), ('anders', 'Anders')],
        'dpv': 'pd:Professional', 'path': ['pd:Occupation', 'sector'],
    },
    'employment_type': {
        'label': 'Dienstverband', 'group': 'occupation', 'input': 'select',
        'options': [('loondienst', 'Loondienst'), ('zzp', 'ZZP'), ('ondernemer', 'Ondernemer'),
                    ('gepensioneerd', 'Gepensioneerd'), ('student', 'Student'), ('anders', 'Anders')],
        'dpv': 'pd:Professional', 'path': ['pd:Occupation', 'employmentType'],
    },
    # -- health (huisartspraktijk bewust niet deelbaar) --
    'smoking_status': {
        'label': 'Rookstatus', 'group': 'health', 'input': 'select',
        'options': [('ja', 'Roker'), ('nee', 'Niet-roker'), ('gestopt', 'Gestopt met roken')],
        'dpv': 'pd:Health', 'path': ['pd:HealthData', 'smokingStatus'],
    },
}

# Doel van een intentie (datamodel punt 2); DPV-koppeling zoals PURPOSE_MAP.
INTENTION_PURPOSES = {
    'quote_calculation': {'label': 'Offerteberekening', 'dpv': 'dpv:ServiceProvision'},
}
DEFAULT_INTENTION_PURPOSE = 'quote_calculation'
OFFER_MODES = ('open', 'targeted')


def attribute_urn(key):
    """urn:mysolido:attribute:<key>"""
    return f'{ATTRIBUTE_URN_PREFIX}{key}'


def _profile_get(profile, path):
    """Lees een waarde uit het profiel-JSON-LD langs een pad; None als het pad ontbreekt."""
    node = profile
    for step in path:
        if isinstance(step, int):
            if not isinstance(node, list) or step >= len(node):
                return None
        elif not isinstance(node, dict) or step not in node:
            return None
        node = node[step]
    return node


def _profile_set(profile, path, value):
    """Schrijf een waarde in het profiel-JSON-LD langs een pad; tussenliggende dicts/lijsten worden aangemaakt."""
    node = profile
    for i, step in enumerate(path[:-1]):
        next_is_index = isinstance(path[i + 1], int)
        if isinstance(step, int):
            while len(node) <= step:
                node.append({})
            if not isinstance(node[step], (dict, list)):
                node[step] = [] if next_is_index else {}
        elif not isinstance(node.get(step), (dict, list)):
            node[step] = [] if next_is_index else {}
        node = node[step]
    node[path[-1]] = value


def profile_attribute_value(profile, key):
    """Ruwe opgeslagen waarde van een attribuut, of None als leeg."""
    value = _profile_get(profile, PROFILE_ATTRIBUTES[key]['path'])
    if value in (None, '', [], {}):
        return None
    return value


def _bool_label(value):
    return 'ja' if value else 'nee'


def attribute_value_label(key, value):
    """Leesbare Nederlandse weergave van een attribuutwaarde."""
    if value is None:
        return ''
    attr = PROFILE_ATTRIBUTES[key]
    kind = attr['input']
    if kind == 'select':
        return dict(attr['options']).get(value, str(value))
    if kind == 'bool':
        return _bool_label(value)
    if kind == 'composite':
        parts = []
        for field in attr['fields'].values():
            sub = value.get(field['json_key']) if isinstance(value, dict) else None
            if sub is None:
                continue
            shown = _bool_label(sub) if field['input'] == 'bool' else str(sub)
            parts.append(f"{field['label']}: {shown}")
        return ', '.join(parts)
    if kind == 'list':
        items = []
        for item in (value if isinstance(value, list) else []):
            if isinstance(item, dict):
                items.append(' - '.join(str(item[k]) for k in attr.get('item_keys', []) if item.get(k)))
            else:
                items.append(str(item))
        return '; '.join(i for i in items if i)
    return str(value)


def extract_profile_attributes(profile):
    """Per groep (volgorde PROFILE_GROUPS) de deelbare attributen met hun actuele waarde."""
    groups = {}
    for key, attr in PROFILE_ATTRIBUTES.items():
        gkey = attr['group']
        if gkey not in groups:
            groups[gkey] = {'label': PROFILE_GROUPS[gkey]['label'], 'icon': PROFILE_GROUPS[gkey]['icon'],
                            'attributes': []}
        value = profile_attribute_value(profile, key)
        groups[gkey]['attributes'].append({
            'key': key, 'urn': attribute_urn(key), 'label': attr['label'],
            'value': value, 'value_label': attribute_value_label(key, value),
            'filled': value is not None,
        })
    return {g: groups[g] for g in PROFILE_GROUPS if g in groups}


def build_shared_attributes(profile, keys, captured_at):
    """Snapshot van de gekozen, gevulde attributen voor een intentierecord (datamodel punt 2)."""
    shared = []
    for key in keys:
        if key not in PROFILE_ATTRIBUTES:
            continue
        value = profile_attribute_value(profile, key)
        if value is None:
            continue
        shared.append({
            '@id': attribute_urn(key),
            'label': PROFILE_ATTRIBUTES[key]['label'],
            'value': value,
            'valueLabel': attribute_value_label(key, value),
            'capturedAt': captured_at,
        })
    return shared


def set_profile_attribute(profile, key, value):
    """Zet een attribuutwaarde op zijn plaats in het profiel-JSON-LD (None wordt overgeslagen)."""
    if value is None:
        return
    _profile_set(profile, PROFILE_ATTRIBUTES[key]['path'], value)


def read_attributes_from_form(form):
    """Lees de attributen met een eigen 'form_field' uit het profielformulier.

    Geeft (waarden per key, labels van ongeldige velden). Lege velden worden overgeslagen.
    """
    values, invalid = {}, []
    for key, attr in PROFILE_ATTRIBUTES.items():
        form_field = attr.get('form_field')
        if not form_field:
            continue
        if attr['input'] == 'composite':
            composite = {}
            for fkey, field in attr['fields'].items():
                raw = (form.get(fkey) or '').strip()
                if not raw:
                    continue
                if field['input'] == 'bool':
                    if raw in ('ja', 'nee'):
                        composite[field['json_key']] = (raw == 'ja')
                elif field['input'] == 'int':
                    try:
                        composite[field['json_key']] = int(raw)
                    except ValueError:
                        invalid.append(field['label'])
                else:
                    composite[field['json_key']] = raw
            if composite:
                values[key] = composite
            continue
        raw = (form.get(form_field) or '').strip()
        if not raw:
            continue
        if attr.get('pattern') and not re.match(attr['pattern'], raw):
            invalid.append(attr['label'])
            continue
        if attr['input'] == 'select' and raw not in dict(attr['options']):
            invalid.append(attr['label'])
            continue
        if attr['input'] == 'int':
            try:
                raw = int(raw)
            except ValueError:
                invalid.append(attr['label'])
                continue
        values[key] = raw
    return values, invalid


def ensure_profiel_policy():
    """Vaste eigenaar-only mappolicy voor profiel/ (ongewijzigd t.o.v. profiel_data_save)."""
    if pod_exists('profiel/.policy.jsonld'):
        return
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
        attributes=PROFILE_ATTRIBUTES,
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
        "@context": dict(PROFILE_CONTEXT),
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

    # Scenario-attributen met eigen formulierveld (PROFILE_ATTRIBUTES: age_category,
    # postal_area, claims_history); ongeldige waarden worden niet opgeslagen
    attr_values, invalid_labels = read_attributes_from_form(form)
    for attr_key, attr_value in attr_values.items():
        set_profile_attribute(profile, attr_key, attr_value)
    for label in invalid_labels:
        flash_t('flash_attribute_invalid', 'error', label=label)

    # Ensure profiel directory exists
    pod_mkdir('profiel')

    # Write profile JSON-LD
    pod_write('profiel/profiel.jsonld',
              _json.dumps(profile, indent=2, ensure_ascii=False))

    # Create ODRL policy if it doesn't exist yet
    ensure_profiel_policy()

    flash_t('flash_profile_saved')
    return redirect(url_for('profiel_data'))


# === INTENTION MODULE (Omgekeerde Google — Fase 2) ===

# profile_fields = voorselectie per categorie, als attribuutsleutels uit PROFILE_ATTRIBUTES
# (tot 20-09-2026 waren dit groepsnamen; sinds subtaak 2 selecteert het formulier per veld)
INTENTION_CATEGORIES = {
    'autoverzekering': {'label': 'Autoverzekering', 'icon': '\U0001f697',
                        'profile_fields': ['age_category', 'postal_area', 'vehicle_type', 'claims_history'],
                        'default_validity': '2w'},   # scenario: geldigheid 2 weken voorgeselecteerd
    'zorgverzekering': {'label': 'Zorgverzekering', 'icon': '\U0001f3e5',
                        'profile_fields': ['age_category', 'smoking_status', 'household_size']},
    'woonverzekering': {'label': 'Woonverzekering', 'icon': '\U0001f3e0',
                        'profile_fields': ['postal_area', 'housing_ownership', 'housing_type', 'insurances']},
    'energiecontract': {'label': 'Energiecontract', 'icon': '\u26a1',
                        'profile_fields': ['postal_area', 'housing_type', 'household_size']},
    'hypotheek': {'label': 'Hypotheek', 'icon': '\U0001f3e6',
                  'profile_fields': ['age_category', 'postal_area', 'housing_ownership', 'work_sector',
                                     'employment_type', 'household_size']},
    'reisverzekering': {'label': 'Reisverzekering', 'icon': '\u2708\ufe0f',
                        'profile_fields': ['age_category', 'household_size', 'children', 'insurances']},
    'rechtsbijstand': {'label': 'Rechtsbijstand', 'icon': '\u2696\ufe0f',
                       'profile_fields': ['employment_type', 'household_size']},
    'pensioen': {'label': 'Pensioen', 'icon': '\U0001f9d3',
                 'profile_fields': ['age_category', 'employment_type', 'household_size']},
    'internet_tv': {'label': 'Internet & TV', 'icon': '\U0001f4e1',
                    'profile_fields': ['postal_area', 'housing_type']},
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

    # Personal (scenario-attribuut age_category, PROFILE_ATTRIBUTES)
    age_category = profile.get('pd:AgeRange', '')
    groups['personal'] = {
        'label': PROFILE_GROUPS['personal']['label'],
        'icon': PROFILE_GROUPS['personal']['icon'],
        'filled': bool(age_category),
        'summary': age_category,
        'data': {'ageCategory': age_category} if age_category else {}
    }

    # Housing
    housing_parts = []
    if profile.get('pd:HousingOwnership'):
        housing_parts.append(profile['pd:HousingOwnership'])
    if profile.get('mysolido:housingType'):
        housing_parts.append(profile['mysolido:housingType'])
    if profile.get('pd:Location'):
        housing_parts.append(profile['pd:Location'])
    if profile.get('pd:PostalCode'):
        housing_parts.append(f"postcodegebied {profile['pd:PostalCode']}")
    groups['housing'] = {
        'label': 'Woonsituatie',
        'icon': '\U0001f3e0',
        'filled': bool(housing_parts),
        'summary': ', '.join(housing_parts),
        'data': {
            'ownership': profile.get('pd:HousingOwnership', ''),
            'type': profile.get('mysolido:housingType', ''),
            'region': profile.get('pd:Location', ''),
            'postalArea': profile.get('pd:PostalCode', ''),
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
    # Schadeverleden (scenario-attribuut claims_history, PROFILE_ATTRIBUTES)
    claims = profile.get('mysolido:claimsHistory')
    if claims:
        ins_parts.append(attribute_value_label('claims_history', claims))
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
        # <uuid>.policy.jsonld is de Offer naast een record, geen intentie
        if fname.endswith('.jsonld') and not fname.startswith('.') and not fname.endswith('.policy.jsonld'):
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
        intent['_date'] = format_date_nl_iso(intent.get('schema:dateCreated', ''))   # dd-mm-jjjj (subtaak 5)
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
        flash_t('flash_not_available_bridge', 'error')
        return redirect(url_for('intenties_overview'))

    if request.method == 'POST':
        category = request.form.get('category', 'anders')
        description = request.form.get('description', '').strip()
        validity = request.form.get('validity', '1m')

        if not description:
            flash_t('flash_description_required', 'error')
            return redirect(url_for('intentie_new'))

        cat_info = INTENTION_CATEGORIES.get(category, INTENTION_CATEGORIES['anders'])
        val_info = VALIDITY_OPTIONS.get(validity, VALIDITY_OPTIONS['1m'])

        now = datetime.now(timezone.utc).replace(microsecond=0)   # hele seconden (subtaak 4a)
        valid_through = now + timedelta(days=val_info['days'])
        intention_id = str(uuid.uuid4())

        # MyTerms-velden (datamodel punt 2): doel, doorleververbod, aanbodvorm
        purpose_code = request.form.get('purpose', DEFAULT_INTENTION_PURPOSE)
        if purpose_code not in INTENTION_PURPOSES:
            purpose_code = DEFAULT_INTENTION_PURPOSE
        purpose_info = INTENTION_PURPOSES[purpose_code]
        no_onward_transfer = request.form.get('no_onward_transfer') is not None
        offer_mode = request.form.get('offer_mode', 'open')
        if offer_mode not in OFFER_MODES:
            offer_mode = 'open'
        targeted_party = request.form.get('targeted_party', '').strip()
        if offer_mode == 'targeted' and not targeted_party:
            flash_t('flash_targeted_party_required', 'error')
            return redirect(url_for('intentie_new'))

        # Snapshot van de gekozen attributen (per veld, waarde van dit moment)
        profile = load_profile_data()
        selected_keys = request.form.getlist('attributes')
        shared_attributes = build_shared_attributes(profile, selected_keys, now.isoformat())
        if not shared_attributes:
            # Een Offer zonder targets is leeg (besluit 20-09, subtaak 3)
            flash_t('flash_attributes_required', 'error')
            return redirect(url_for('intentie_new'))

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
            "mysolido:sharedAttributes": shared_attributes,
            "mysolido:purpose": {
                "@id": f"urn:mysolido:purpose:{purpose_code}",
                "label": purpose_info['label'],
                "dpv": purpose_info['dpv'],
            },
            "mysolido:noOnwardTransfer": no_onward_transfer,
            "mysolido:offerMode": offer_mode,
            "mysolido:policy": intention_policy_uid(intention_id),
        }
        if offer_mode == 'targeted':
            # Partij-id nu al vast, zodat Offer (assignee) en subtaak 4 dezelfde id gebruiken
            record["mysolido:targetedParty"] = {"@id": generate_party_id(), "name": targeted_party}

        pod_mkdir('intenties')
        pod_write(f'intenties/{intention_id}.jsonld',
                  _json.dumps(record, indent=2, ensure_ascii=False))
        ensure_intenties_policy()
        # ODRL-Offer naast het record (subtaak 3)
        write_intention_policy(record)

        flash_t('flash_intention_saved', 'success', label=cat_info["label"])
        log_action('intention_create', {'id': intention_id, 'category': category,
                                        'attributes': [a['@id'] for a in shared_attributes],
                                        'policy': record["mysolido:policy"]})
        return redirect(url_for('intenties_overview'))

    # GET: show form
    profile = load_profile_data()
    attribute_groups = extract_profile_attributes(profile)

    return render_template('intentie_nieuw.html',
        categories=INTENTION_CATEGORIES,
        validity_options=VALIDITY_OPTIONS,
        attribute_groups=attribute_groups,
        purposes=INTENTION_PURPOSES,
        default_purpose=DEFAULT_INTENTION_PURPOSE,
    )


@app.route('/intenties/<intention_id>')
def intentie_detail(intention_id):
    """View a single intention"""
    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash_t('flash_intentions_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_intention_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['_id'] = intention_id
    cat_key = record.get('mysolido:category', 'anders')
    cat_info = INTENTION_CATEGORIES.get(cat_key, INTENTION_CATEGORIES['anders'])
    record['_icon'] = cat_info['icon']
    record['_category_label'] = cat_info['label']
    record['_status'] = record.get('mysolido:status', 'concept')

    # Snapshot (datamodel punt 2): de detailpagina toont wat bij aanmaken is vastgelegd.
    # Records van vóór 20-09-2026 hebben mysolido:sharedProfileData (per groep) en
    # vallen terug op de groepsweergave met het actuele profiel.
    shared_attributes = record.get('mysolido:sharedAttributes')
    legacy_shared = None
    profile_groups = {}
    if shared_attributes is None and isinstance(record.get('mysolido:sharedProfileData'), dict):
        legacy_shared = record['mysolido:sharedProfileData']
        profile_groups = extract_profile_groups(load_profile_data())
    captured_at = ''
    if shared_attributes:
        captured_at = shared_attributes[0].get('capturedAt', '')
    captured_at = captured_at or record.get('schema:dateCreated', '')

    # ODRL-Offer naast het record (subtaak 3); ook zichtbaar in Bridge-modus
    policy = load_intention_policy(intention_id)
    policy_summary = intention_policy_summary_nl(policy, record) if policy else ''

    # Gesloten Agreements (subtaak 4a): "Geaccepteerd door <partij> op <datum>"
    accepted_by = accepted_requests_for(record)

    # Aanbodlink (subtaak 5): de volledige URL van het acceptatieformulier, lokaal met de
    # host van dit verzoek, op de Bridge met SHARE_BASE_URL uit .env
    if BRIDGE_MODE:
        offer_base = os.getenv('SHARE_BASE_URL', '').strip().rstrip('/') or request.host_url.rstrip('/')
    else:
        offer_base = request.host_url.rstrip('/')
    offer_url = offer_base + url_for('verzoek_intentie', intention_id=intention_id)

    return render_template('intentie_detail.html',
        intention=record,
        shared_attributes=shared_attributes or [],
        captured_at=format_date_nl_iso(captured_at),
        legacy_shared=legacy_shared,
        profile_groups=profile_groups,
        policy=policy,
        policy_summary=policy_summary,
        accepted_by=accepted_by,
        offer_url=offer_url,
        read_only=BRIDGE_MODE,
    )


@app.route('/intenties/<intention_id>/policy.jsonld')
def intentie_policy_file(intention_id):
    """De Offer van een intentie als application/ld+json.

    Op de Bridge openbaar zolang de intentie actief is (BRIDGE_PUBLIC_ENDPOINTS); anders na eigenaarslogin.
    """
    path = safe_pod_path(intention_policy_relpath(intention_id))
    if not path or not os.path.isfile(path):
        abort(404)
    with open(path, 'r', encoding='utf-8') as f:
        return Response(f.read(), mimetype='application/ld+json')


@app.route('/intenties/<intention_id>/policy/create', methods=['POST'])
def intentie_policy_create(intention_id):
    """Maak de Offer alsnog voor een record zonder policybestand ("Voorwaarden opstellen")."""
    if BRIDGE_MODE:
        abort(403)

    intenties_dir = get_intenties_dir()
    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld") if intenties_dir else None
    if not fpath or not os.path.exists(fpath):
        flash_t('flash_intention_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    if not record.get('mysolido:sharedAttributes'):
        flash_t('flash_policy_no_attributes', 'error')
        return redirect(url_for('intentie_detail', intention_id=intention_id))

    write_intention_policy(record)
    if record.get('mysolido:policy') != intention_policy_uid(intention_id):
        record['mysolido:policy'] = intention_policy_uid(intention_id)
        with open(fpath, 'w', encoding='utf-8') as f:
            _json.dump(record, f, indent=2, ensure_ascii=False)

    flash_t('flash_policy_created')
    log_action('intention_policy_create', {'id': intention_id, 'policy': record['mysolido:policy']})
    return redirect(url_for('intentie_detail', intention_id=intention_id))


@app.route('/intenties/<intention_id>/activate', methods=['POST'])
def intentie_activate(intention_id):
    """Activate an intention"""
    if BRIDGE_MODE:
        abort(403)

    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash_t('flash_intentions_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_intention_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['mysolido:status'] = 'actief'
    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=2, ensure_ascii=False)

    flash_t('flash_intention_activated')
    log_action('intention_activate', {'id': intention_id})
    return redirect(url_for('intentie_detail', intention_id=intention_id))


@app.route('/intenties/<intention_id>/withdraw', methods=['POST'])
def intentie_withdraw(intention_id):
    """Withdraw an intention"""
    if BRIDGE_MODE:
        abort(403)

    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash_t('flash_intentions_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_intention_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['mysolido:status'] = 'ingetrokken'
    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump(record, f, indent=2, ensure_ascii=False)

    flash_t('flash_intention_withdrawn')
    log_action('intention_withdraw', {'id': intention_id})
    return redirect(url_for('intentie_detail', intention_id=intention_id))


@app.route('/intenties/<intention_id>/delete', methods=['POST'])
def intentie_delete(intention_id):
    """Delete an intention"""
    if BRIDGE_MODE:
        abort(403)

    intenties_dir = get_intenties_dir()
    if not intenties_dir:
        flash_t('flash_intentions_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    fpath = os.path.join(intenties_dir, f"{intention_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_intention_not_found', 'error')
        return redirect(url_for('intenties_overview'))

    # Een intentie met gesloten Agreement(s) blijft staan (subtaak 4a)
    with open(fpath, 'r', encoding='utf-8') as f:
        existing = _json.load(f)
    if existing.get('mysolido:acceptedBy'):
        flash_t('flash_intention_has_agreements', 'error')
        return redirect(url_for('intentie_detail', intention_id=intention_id))

    os.remove(fpath)
    # De Offer naast het record gaat mee (subtaak 3)
    policy_path = safe_pod_path(intention_policy_relpath(intention_id))
    if policy_path and os.path.isfile(policy_path):
        os.remove(policy_path)
    flash_t('flash_intention_deleted')
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
# Instelbaar via .env (REQUEST_RATE_LIMIT, standaard 10 per uur per IP), zodat een
# demo-oefenmiddag met veel acceptaties vanaf één laptop niet vastloopt (subtaak 5)
REQUEST_RATE_LIMIT = int(os.getenv('REQUEST_RATE_LIMIT', '10') or 10)


def is_rate_limited(ip, max_requests=None, window_seconds=3600):
    """Check and enforce rate limit: max requests per window per IP"""
    if max_requests is None:
        max_requests = REQUEST_RATE_LIMIT
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
        # <uuid>.agreement.jsonld is de Agreement naast een verzoek, geen verzoek (subtaak 4a)
        if fname.endswith('.jsonld') and not fname.startswith('.') and not fname.endswith('.agreement.jsonld'):
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
        # 'wacht-op-bevestiging' telt mee: een gerichte acceptatie vraagt om bevestiging (4b)
        return sum(1 for r in reqs if r.get('mysolido:status') in ('nieuw', REQUEST_STATUS_AWAITING))
    except Exception:
        return 0


def find_request_by_status_token(token):
    """Find a request record by its status token"""
    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir or not os.path.isdir(verzoeken_dir):
        return None, None

    for fname in os.listdir(verzoeken_dir):
        if fname.endswith('.jsonld') and not fname.startswith('.') and not fname.endswith('.agreement.jsonld'):
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
        flash_t('flash_rate_limit', 'error')
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
        flash_t('flash_required_fields', 'error')
        return redirect(url_for('verzoek_formulier'))

    if not agreed:
        flash_t('flash_agree_terms', 'error')
        return redirect(url_for('verzoek_formulier'))

    if not requested_data:
        flash_t('flash_select_data', 'error')
        return redirect(url_for('verzoek_formulier'))

    # Basic email validation
    if '@' not in email or '.' not in email:
        flash_t('flash_invalid_email', 'error')
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

    # Check if approved/accepted response has expired ('geaccepteerd' sinds subtaak 4a)
    if status in REQUEST_STATUSES_WITH_RESPONSE and valid_until:
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
        withdrawn_at=format_date_nl_iso(record.get('mysolido:withdrawnAt', '')),   # toestemming ingetrokken (4b)
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

    if status == REQUEST_STATUS_WITHDRAWN:
        # Toestemming ingetrokken (subtaak 4b): geen gegevens meer, alleen de intrekdatum
        # en (subtaak 5) de Agreement-uid als verwijzing naar het bewijs
        return render_template('verzoek_response.html', found=True, expired=False, withdrawn=True,
                               withdrawn_at=format_date_nl_iso(record.get('mysolido:withdrawnAt', '')),
                               agreement_uid=record.get('mysolido:agreement', ''))

    if status not in REQUEST_STATUSES_WITH_RESPONSE:
        return render_template('verzoek_response.html', found=False), 404

    # Check expiry
    if valid_until:
        try:
            exp_dt = datetime.fromisoformat(valid_until)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                return render_template('verzoek_response.html', found=True, expired=True,
                                       valid_until=format_date_nl_iso(valid_until))
        except (ValueError, TypeError):
            pass

    # Load the response data
    request_id = record['_id']
    response_path = safe_pod_path(f'verzoeken/{request_id}_response.json')
    if not response_path or not os.path.exists(response_path):
        return render_template('verzoek_response.html', found=False), 404

    with open(response_path, 'r', encoding='utf-8') as f:
        response_data = _json.load(f)

    # Intentiegebonden verzoek (subtaak 4a): uitsluitend de vastgelegde attributen,
    # met de samenvattingszin van de Agreement en de Agreement-uid erboven
    agreement = None
    agreement_summary = ''
    if 'attributes' in response_data:
        agreement = load_agreement(request_id)
        intention_id = str(record.get('mysolido:intention', '')).rsplit(':', 1)[-1]
        intention_record = load_intention_record(intention_id) or {}
        agreement_summary = intention_policy_summary_nl(agreement, intention_record) if agreement else ''

    return render_template('verzoek_response.html',
        found=True,
        expired=False,
        response_data=response_data,
        agreement=agreement,
        agreement_summary=agreement_summary,
        valid_until=format_date_nl_iso(valid_until) if valid_until else '',
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
        req['_date'] = format_date_nl_iso(req.get('schema:dateCreated', ''))   # dd-mm-jjjj (subtaak 5)
        req['_requested_data'] = req.get('mysolido:requestedData', [])
        if req.get('mysolido:intention'):
            # intentiegebonden verzoek (subtaak 4a): attribuut-urn's als labels tonen
            req['_requested_data'] = [attribute_label_from_urn(u) for u in req['_requested_data']]

    return render_template('verzoeken.html', requests=requests_list)


@app.route('/verzoeken/<request_id>')
def verzoek_detail_owner(request_id):
    """Detail view of a consent request (owner only)"""
    if BRIDGE_MODE:
        abort(403)

    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir:
        flash_t('flash_requests_not_found', 'error')
        return redirect(url_for('verzoeken_overview'))

    fpath = os.path.join(verzoeken_dir, f"{request_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_request_not_found', 'error')
        return redirect(url_for('verzoeken_overview'))

    with open(fpath, 'r', encoding='utf-8') as f:
        record = _json.load(f)

    record['_id'] = request_id
    record['_status'] = record.get('mysolido:status', 'nieuw')

    # Load profile data for approval form
    profile = load_profile_data()
    profile_groups = extract_profile_groups(profile)

    # Intentiegebonden verzoek (subtaak 4a): voorwaarden, partij, tijdstip, hash, Agreement
    acceptance = None
    if record.get('mysolido:intention'):
        intention_id = str(record['mysolido:intention']).rsplit(':', 1)[-1]
        intention_record = load_intention_record(intention_id) or {}
        agreement = load_agreement(request_id)
        offer = load_intention_policy(intention_id)
        acceptance = {
            'intention_id': intention_id,
            'intention_label': intention_record.get('mysolido:categoryLabel', ''),
            'intention_status': intention_record.get('mysolido:status', ''),
            'offer_mode': intention_record.get('mysolido:offerMode', 'open'),
            'targeted_party': (intention_record.get('mysolido:targetedParty') or {}).get('name', ''),
            'summary': intention_policy_summary_nl(agreement or offer, intention_record) if (agreement or offer) else '',
            'party': record.get('mysolido:party') or {},
            'accepted_at': format_date_nl_iso(record.get('mysolido:acceptedAt', '')),
            'accepted_at_raw': record.get('mysolido:acceptedAt', ''),
            'accepted_policy': record.get('mysolido:acceptedPolicy', ''),
            'policy_hash': record.get('mysolido:acceptedPolicyHash', ''),
            'agreement': agreement,
            'attributes': [attribute_label_from_urn(u) for u in record.get('mysolido:requestedData', [])],
            # gedeelde waarden uit de response en het consentrecord (subtaak 4b)
            'shared': (load_pod_json(request_response_relpath(request_id)) or {}).get('attributes', []),
            'consent_id': str(record.get('mysolido:consent', '')).rsplit(':', 1)[-1],
            'withdrawn_at': format_date_nl_iso(record.get('mysolido:withdrawnAt', '')),
        }

    return render_template('verzoek_detail.html',
        req=record,
        profile_groups=profile_groups,
        approval_validity=APPROVAL_VALIDITY,
        acceptance=acceptance,
    )


@app.route('/verzoeken/<request_id>/approve', methods=['POST'])
def verzoek_approve(request_id):
    """Approve a consent request (owner only)"""
    if BRIDGE_MODE:
        abort(403)

    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir:
        flash_t('flash_requests_not_found', 'error')
        return redirect(url_for('verzoeken_overview'))

    fpath = os.path.join(verzoeken_dir, f"{request_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_request_not_found', 'error')
        return redirect(url_for('verzoeken_overview'))

    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            record = _json.load(f)

        # Intentiegebonden verzoek bij een gericht aanbod (subtaak 4a): de eigenaar bevestigt
        # dat dit de benoemde partij is; dan pas ontstaat de Agreement. Verzoeken zonder
        # intentie volgen het bestaande pad hieronder.
        if record.get('mysolido:intention'):
            return confirm_targeted_acceptance(record, request_id)

        # Get approved data groups from form
        approved_groups = request.form.getlist('approved_data')
        validity_key = request.form.get('validity', '1w')
        val_info = APPROVAL_VALIDITY.get(validity_key, APPROVAL_VALIDITY['1w'])

        if not approved_groups:
            flash_t('flash_select_data_share', 'error')
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

        # Generieke goedkeuring (verzoek zonder intentie): er wordt bewust géén consentrecord
        # geschreven. Alleen intentiegebonden acceptaties krijgen een 27560-record, via
        # conclude_agreement() (subtaak 4b). Zie ontwikkeling/archief/mysolido_verslag_myterms-demo-subtaak4b.
        log_action('request_approve_generic', {'id': request_id, 'consent_record': None,
                                               'note': 'generieke goedkeuring zonder consentrecord'})
        requester = record.get('mysolido:requester', {})
        requester_name = requester.get('schema:name', 'Onbekend')
        requester_org = requester.get('schema:worksFor', '')
        receiver_label = f"{requester_name} ({requester_org})" if requester_org else requester_name

        flash_t('flash_request_approved', 'success', name=receiver_label)
        log_action('request_approve', {
            'id': request_id,
            'requester': requester_name,
            'approved_data': approved_groups,
            'valid_until': valid_until.isoformat(),
        })
        return redirect(url_for('verzoek_detail_owner', request_id=request_id))

    except Exception as e:
        send_crash_report("approval_failed", str(e), "verzoek goedkeuren")
        flash_t('flash_approve_failed', 'error')
        return redirect(url_for('verzoeken_overview'))


@app.route('/verzoeken/<request_id>/reject', methods=['POST'])
def verzoek_reject(request_id):
    """Reject a consent request (owner only)"""
    if BRIDGE_MODE:
        abort(403)

    verzoeken_dir = get_verzoeken_dir()
    if not verzoeken_dir:
        flash_t('flash_requests_not_found', 'error')
        return redirect(url_for('verzoeken_overview'))

    fpath = os.path.join(verzoeken_dir, f"{request_id}.jsonld")
    if not os.path.exists(fpath):
        flash_t('flash_request_not_found', 'error')
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
    flash_t('flash_request_rejected', 'success', name=requester_name)
    log_action('request_reject', {'id': request_id, 'requester': requester_name})
    return redirect(url_for('verzoeken_overview'))


# === ACCEPTATIE VIA INTENTIE: routes (MyTerms-demo, subtaak 4a) ===
# Publiek formulier aan een intentie: voorwaarden lezen (ook op de Bridge), accepteren
# alleen lokaal en alleen bij een actieve intentie. Het generieke /verzoek blijft bestaan.

def _intention_form_context(intention_id):
    """Alles wat het intentiegebonden formulier nodig heeft; None als de intentie ontbreekt."""
    record = load_intention_record(intention_id)
    if not record:
        return None
    policy = load_intention_policy(intention_id)
    return {
        'intention': record,
        'intention_id': intention_id,
        'status': record.get('mysolido:status', 'concept'),
        'policy': policy,
        'policy_summary': intention_policy_summary_nl(policy, record) if policy else '',
        'attribute_labels': [a.get('label', '') for a in record.get('mysolido:sharedAttributes', [])],
        'offer_mode': record.get('mysolido:offerMode', 'open'),
        'targeted_party': (record.get('mysolido:targetedParty') or {}).get('name', ''),
        'valid_through': format_date_nl_iso(record.get('schema:validThrough', '')),
    }


def _acceptance_party(intention, name, organization, email):
    """Partij-object voor het verzoek: nieuw id bij open aanbod, het benoemde id bij gericht aanbod."""
    if intention.get('mysolido:offerMode') == 'targeted':
        party_id = (intention.get('mysolido:targetedParty') or {}).get('@id') or generate_party_id()
    else:
        party_id = generate_party_id()
    # In MyTerms is de wederpartij de organisatie: label = organisatie als die is ingevuld,
    # anders de naam; de persoon staat apart als contactName (besluit 20-09, subtaak 4b)
    return {"@id": party_id, "rdfs:label": organization or name, "mysolido:contactName": name,
            "mysolido:organisation": organization, "mysolido:contact": email}


def _build_acceptance_request(intention, policy, party, request_id, status_token):
    """Verzoekrecord (mysolido:ConsentRequest) voor een acceptatie van een intentie-Offer."""
    intention_id = intention_id_from_record(intention)
    return {
        "@context": {
            "mysolido": "https://mysolido.com/vocab#",
            "dpv": "https://w3id.org/dpv#",
            "schema": "https://schema.org/",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "xsd": "http://www.w3.org/2001/XMLSchema#"
        },
        "@type": "mysolido:ConsentRequest",
        "@id": f"urn:mysolido:request:{request_id}",
        "mysolido:statusToken": status_token,
        "mysolido:status": REQUEST_STATUS_AWAITING,
        "schema:dateCreated": utc_now_iso_seconds(),
        "mysolido:requester": {
            "schema:name": party.get('mysolido:contactName') or party['rdfs:label'],   # de persoon (subtaak 5)
            "schema:worksFor": party['mysolido:organisation'],
            "schema:email": party['mysolido:contact'],
        },
        "mysolido:category": intention.get('mysolido:category', 'anders'),
        "mysolido:categoryLabel": intention.get('mysolido:categoryLabel', ''),
        "mysolido:requestedData": [a.get('@id') for a in intention.get('mysolido:sharedAttributes', [])],
        "mysolido:purpose": (intention.get('mysolido:purpose') or {}).get('label', ''),
        "mysolido:agreedToTerms": True,
        "mysolido:intention": intention.get('@id', ''),
        "mysolido:acceptedPolicy": policy.get('uid', ''),
        "mysolido:acceptedAt": utc_now_iso_seconds(),
        "mysolido:acceptedPolicyHash": sha256_of_pod_file(intention_policy_relpath(intention_id)),
        "mysolido:party": party,
        "mysolido:approvedData": None,
        "mysolido:responseLink": None,
        "mysolido:validUntil": None,
        "mysolido:rejectionReason": None,
    }


@app.route('/verzoek/intentie/<intention_id>', methods=['GET', 'POST'])
def verzoek_intentie(intention_id):
    """Voorwaarden van een intentie lezen en accepteren (publiek; accepteren alleen lokaal)."""
    ctx = _intention_form_context(intention_id)
    if ctx is None:
        return render_template('verzoek_intentie.html', found=False), 404

    acceptable = ctx['status'] == 'actief' and ctx['policy'] is not None and not BRIDGE_MODE

    if request.method == 'GET':
        return render_template('verzoek_intentie.html', found=True, acceptable=acceptable,
                               bridge_mode=BRIDGE_MODE, **ctx)

    # POST: accepteren
    if BRIDGE_MODE:
        flash_t('flash_bridge_accept_blocked', 'error')
        return redirect(url_for('verzoek_intentie', intention_id=intention_id))
    if ctx['policy'] is None:
        flash_t('flash_no_terms', 'error')
        return redirect(url_for('verzoek_intentie', intention_id=intention_id))
    if ctx['status'] != 'actief':
        flash_t('flash_intention_not_active', 'error')
        return redirect(url_for('verzoek_intentie', intention_id=intention_id))

    client_ip = request.remote_addr or 'unknown'
    if is_rate_limited(client_ip):
        flash_t('flash_rate_limit', 'error')
        return redirect(url_for('verzoek_intentie', intention_id=intention_id))

    name = sanitize_input(request.form.get('name', ''))
    organization = sanitize_input(request.form.get('organization', ''))
    email = sanitize_input(request.form.get('email', ''))
    accepted = request.form.get('accept_terms') == 'yes'

    if not name or not email:
        flash_t('flash_required_fields', 'error')
        return redirect(url_for('verzoek_intentie', intention_id=intention_id))
    if '@' not in email or '.' not in email:
        flash_t('flash_invalid_email', 'error')
        return redirect(url_for('verzoek_intentie', intention_id=intention_id))
    if not accepted:
        flash_t('flash_accept_terms_required', 'error')
        return redirect(url_for('verzoek_intentie', intention_id=intention_id))

    intention = ctx['intention']
    request_id = str(uuid.uuid4())
    status_token = str(uuid.uuid4())
    party = _acceptance_party(intention, name, organization, email)
    record = _build_acceptance_request(intention, ctx['policy'], party, request_id, status_token)

    pod_mkdir('verzoeken')
    ensure_verzoeken_policy()
    if intention.get('mysolido:offerMode') == 'targeted':
        # Registreren; de eigenaar bevestigt in verzoek_approve() dat dit de benoemde partij is
        save_pod_json(f'verzoeken/{request_id}.jsonld', record)
        log_action('request_accept_pending', {'id': request_id, 'intention': intention_id, 'party': party['@id']})
        return render_template('verzoek_bevestiging.html', status_token=status_token,
                               accepted=True, awaiting=True, response_link=None)

    conclude_agreement(record, intention)
    return render_template('verzoek_bevestiging.html', status_token=status_token,
                           accepted=True, awaiting=False, response_link=record.get('mysolido:responseLink'))


def confirm_targeted_acceptance(record, request_id):
    """Eigenaar bevestigt een gericht aanbod (aangeroepen vanuit verzoek_approve)."""
    if record.get('mysolido:status') != REQUEST_STATUS_AWAITING:
        flash_t('flash_request_already_handled', 'error')
        return redirect(url_for('verzoek_detail_owner', request_id=request_id))
    intention_id = str(record.get('mysolido:intention', '')).rsplit(':', 1)[-1]
    intention = load_intention_record(intention_id)
    if not intention:
        flash_t('flash_intention_not_found', 'error')
        return redirect(url_for('verzoek_detail_owner', request_id=request_id))
    if intention.get('mysolido:offerMode') != 'targeted':
        flash_t('flash_request_already_handled', 'error')
        return redirect(url_for('verzoek_detail_owner', request_id=request_id))
    if intention.get('mysolido:status') != 'actief':
        flash_t('flash_intention_not_active', 'error')
        return redirect(url_for('verzoek_detail_owner', request_id=request_id))

    conclude_agreement(record, intention)
    party_label = (record.get('mysolido:party') or {}).get('rdfs:label', '')
    flash_t('flash_request_confirmed', 'success', name=party_label)
    log_action('request_approve', {'id': request_id, 'requester': party_label,
                                   'agreement': record.get('mysolido:agreement', '')})
    return redirect(url_for('verzoek_detail_owner', request_id=request_id))


@app.route('/verzoeken/<request_id>/agreement.jsonld')
def verzoek_agreement_file(request_id):
    """De Agreement van een verzoek als application/ld+json (eigenaarslogin; ook in Bridge-modus)."""
    path = safe_pod_path(agreement_relpath(request_id))
    if not path or not os.path.isfile(path):
        abort(404)
    with open(path, 'r', encoding='utf-8') as f:
        return Response(f.read(), mimetype='application/ld+json')


# === Crash report endpoints (Bridge) ===

_crash_report_rate_limit = {}


def is_crash_rate_limited(ip, max_requests=10, window_seconds=3600):
    """Rate limit crash reports: max 10 per hour per IP"""
    now = time.time()
    timestamps = _crash_report_rate_limit.get(ip, [])
    timestamps = [t for t in timestamps if now - t < window_seconds]
    if len(timestamps) >= max_requests:
        _crash_report_rate_limit[ip] = timestamps
        return True
    timestamps.append(now)
    _crash_report_rate_limit[ip] = timestamps
    return False


def get_crash_reports_dir():
    """Return the crash-reports directory path"""
    if BRIDGE_MODE:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'crash-reports')
    return os.path.join(PROJECT_DIR, 'crash-reports')


@app.route('/crash-report', methods=['POST'])
def crash_report_receive():
    """Receive an anonymous crash report (public, no auth required)"""
    if not BRIDGE_MODE:
        abort(404)

    if is_crash_rate_limited(request.remote_addr):
        return {'status': 'rate_limited'}, 429

    data = request.get_json(silent=True)
    if not data:
        return {'status': 'invalid'}, 400

    required_fields = ['timestamp', 'version', 'error_type', 'error_message']
    if not all(f in data for f in required_fields):
        return {'status': 'missing_fields'}, 400

    report = {
        'timestamp': sanitize_input(str(data.get('timestamp', ''))[:50]),
        'version': sanitize_input(str(data.get('version', ''))[:20]),
        'os': sanitize_input(str(data.get('os', ''))[:50]),
        'os_version': sanitize_input(str(data.get('os_version', ''))[:100]),
        'python_version': sanitize_input(str(data.get('python_version', ''))[:20]),
        'error_type': sanitize_input(str(data.get('error_type', ''))[:200]),
        'error_message': sanitize_input(str(data.get('error_message', ''))[:500]),
        'context': sanitize_input(str(data.get('context', ''))[:200]),
    }

    crash_dir = get_crash_reports_dir()
    os.makedirs(crash_dir, exist_ok=True)

    safe_timestamp = re.sub(r'[^a-zA-Z0-9_\-]', '_', report['timestamp'][:30])
    safe_error_type = re.sub(r'[^a-zA-Z0-9_\-]', '_', report['error_type'][:50])
    filename = f"{safe_timestamp}_{safe_error_type}.json"

    filepath = os.path.join(crash_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        _json.dump(report, f, indent=2, ensure_ascii=False)

    return {'status': 'received'}, 200


@app.route('/crash-reports')
def crash_reports_overview():
    """Show crash reports overview (Bridge login required)"""
    if not BRIDGE_MODE:
        abort(404)

    crash_dir = get_crash_reports_dir()
    reports = []

    if os.path.isdir(crash_dir):
        for fname in os.listdir(crash_dir):
            if fname.endswith('.json'):
                fpath = os.path.join(crash_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        report = _json.load(f)
                    report['_filename'] = fname
                    reports.append(report)
                except (_json.JSONDecodeError, IOError):
                    continue

    reports.sort(key=lambda r: r.get('timestamp', ''), reverse=True)
    return render_template('crash_reports.html', reports=reports)


@app.route('/crash-reports/delete/<filename>', methods=['POST'])
def crash_report_delete(filename):
    """Delete a crash report (Bridge login required)"""
    if not BRIDGE_MODE:
        abort(404)

    safe_filename = re.sub(r'[^a-zA-Z0-9_\-.]', '', filename)
    if not safe_filename.endswith('.json'):
        abort(400)

    crash_dir = get_crash_reports_dir()
    fpath = os.path.join(crash_dir, safe_filename)

    if os.path.exists(fpath) and os.path.dirname(os.path.abspath(fpath)) == os.path.abspath(crash_dir):
        os.remove(fpath)
        flash_t('flash_report_deleted')
    else:
        flash_t('flash_report_not_found', 'error')

    return redirect(url_for('crash_reports_overview'))


# ---------------------------------------------------------------------------
# AI-assistent (Fase 4 — Lokale LLM op pod-data)
# ---------------------------------------------------------------------------

@app.route('/ai')
def ai_chat():
    """AI-assistent chatvenster"""
    if BRIDGE_MODE:
        abort(403)
    return render_template('ai_chat.html')


@app.route('/ai/ask', methods=['POST'])
def ai_ask():
    """Beantwoord een vraag via de lokale AI"""
    if BRIDGE_MODE:
        abort(403)

    from flask import jsonify
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({"answer": "Stel een vraag.", "sources": []}), 400

    try:
        import ai_service
        result = ai_service.ask(question)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"answer": f"Er ging iets mis: {exc}", "sources": []}), 500


@app.route('/ai/index', methods=['POST'])
def ai_index():
    """Bouw de AI-zoekindex op over alle pod-documenten"""
    if BRIDGE_MODE:
        abort(403)

    from flask import jsonify
    try:
        import ai_service
        pod_path = get_pod_data_path()
        result = ai_service.index_all_documents(pod_path)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/ai/status')
def ai_status():
    """Status van Ollama en de zoekindex"""
    if BRIDGE_MODE:
        abort(403)

    from flask import jsonify
    try:
        import ai_service
        ai = ai_service.check_ai_status()
        index = ai_service.get_index_stats()
        missing = ai_service.get_missing_dependencies()
        return jsonify({"ollama": ai["ollama"], "index": index, "missing_deps": missing,
                        "provider": ai["provider"], "claude_configured": ai["claude_configured"],
                        "claude_model": ai["claude_model"]})
    except Exception as exc:
        return jsonify({"ollama": {"running": False, "error": str(exc)}, "index": {"total_chunks": 0, "status": "error"}, "missing_deps": {},
                        "provider": "local", "claude_configured": False, "claude_model": None}), 500


@app.errorhandler(403)
def forbidden_error(error):
    """B8 (21-09-2026): geen kale Engelse Flask-pagina meer; in Bridge-modus zijn schrijf- en
    eigenaarsroutes bewust afgesloten."""
    return render_template('error.html', heading=translate('error_403_heading'),
                           error=translate('error_403_bridge' if BRIDGE_MODE else 'error_403_text')), 403


@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', heading=translate('error_404_heading'),
                           error=translate('error_404_text')), 404


@app.errorhandler(500)
def internal_error(error):
    send_crash_report("internal_server_error", str(error), request.path[:200])
    return render_template('error.html', error="Er is een interne fout opgetreden."), 500


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
        print(f"  Start op http://127.0.0.1:{APP_PORT}  (versie {APP_VERSION})")
        print("  ========================")
        print()
        app.run(port=APP_PORT, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
    else:
        print("  === MySolido ===")

        if not auto_setup():
            print()
            print("  Setup mislukt. Zorg dat Community Solid Server draait op poort 3000:")
            print("  npm install   (eenmalig, installeert de versie uit package.json)")
            print("  node node_modules/@solid/community-server/bin/server.js -p 3000 -b http://127.0.0.1:3000 -f .data/ -c @css:config/file.json")
            print()
            exit(1)

        # Initialize default ODRL policies for all standard folders
        init_default_policies()

        # Clean up old watermark temp files
        cleanup_temp_files()

        print()
        print(f"  Pod: {os.getenv('SOLID_POD_URL')}")
        print(f"  Start op http://localhost:{APP_PORT}  (versie {APP_VERSION})")
        print("  ================")
        print()

        app.run(port=APP_PORT, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
