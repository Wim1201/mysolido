import re
import os
import io
import time
import secrets
import string
import zipfile
import shutil
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote
from flask import Flask, render_template, request, redirect, url_for, flash, Response
import requests
import base64
from dotenv import load_dotenv
from audit import log_action, get_audit_log
from shares import add_share, remove_share, get_all_shares, get_shares_for_resource, check_expired_shares
from trash import move_to_trash, restore_from_trash, permanent_delete, get_all_trash, cleanup_expired
from notifications import add_notification, get_all_notifications, get_unread_count, mark_as_read, mark_all_read

load_dotenv()

app = Flask(__name__)
app.secret_key = 'mysolido-dev-key-2026'

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


def generate_password(length=32):
    """Genereer een veilig wachtwoord"""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def auto_setup():
    """Automatische setup bij eerste start"""
    global CLIENT_ID, CLIENT_SECRET, CSS_BASE_URL, SOLID_POD_URL, WEBID, OWNER_WEBID

    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

    # Check of .env al bestaat met geldige credentials
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
        if os.getenv('CLIENT_ID') and os.getenv('CLIENT_SECRET'):
            print("  [OK] Bestaande configuratie gevonden")
            return True

    print("  Eerste keer opstarten \u2014 account wordt aangemaakt...")

    css_base = os.getenv('CSS_BASE_URL', 'http://127.0.0.1:3000')

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
            time.sleep(2)

        if not css_ready:
            print("  [FOUT] Community Solid Server is niet bereikbaar op poort 3000")
            return False

        initial_controls = r.json().get('controls', {})

        # Stap 2: Maak account aan
        create_url = initial_controls.get('account', {}).get('create')
        if not create_url:
            print("  [FOUT] Geen account-create URL gevonden in CSS API")
            return False

        r = requests.post(create_url,
            headers={'Content-Type': 'application/json'},
            json={})

        if r.status_code not in [200, 201]:
            print(f"  [FOUT] Account aanmaken mislukt: {r.status_code}")
            return False

        data = r.json()
        authorization = data.get('authorization')
        if not authorization:
            print("  [FOUT] Geen authorization token ontvangen")
            return False

        # Stap 3: Haal volledige controls op met authorization token
        r = requests.get(f'{css_base}/.account/',
            headers={
                'Authorization': f'CSS-Account-Token {authorization}',
                'Accept': 'application/json'
            })

        if r.status_code != 200:
            print(f"  [FOUT] Account controls ophalen mislukt: {r.status_code}")
            return False

        full_controls = r.json().get('controls', {})

        # Stap 4: Registreer email/wachtwoord
        # In CSS v7.1.8 heet dit 'password.create', niet 'password.register'
        password_create_url = full_controls.get('password', {}).get('create')
        if not password_create_url:
            print("  [FOUT] Geen password-create URL gevonden in CSS API")
            print(f"  [DEBUG] Beschikbare password controls: {list(full_controls.get('password', {}).keys())}")
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
            print(f"  [FOUT] Wachtwoord registreren mislukt: {r.status_code}")
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
            print(f"  [FOUT] Pod aanmaken mislukt: {r.status_code}")
            return False

        pod_url = f'{css_base}/{pod_name}/'
        webid = f'{pod_url}profile/card#me'

        # Stap 6: Genereer client credentials
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
                'name': 'MySolido App',
                'webId': webid
            })

        if r.status_code not in [200, 201]:
            print(f"  [FOUT] Client credentials aanmaken mislukt: {r.status_code}")
            return False

        cred_data = r.json()
        client_id = cred_data.get('id')
        client_secret = cred_data.get('secret')

        if not client_id or not client_secret:
            print("  [FOUT] Geen client credentials ontvangen")
            return False

        # Stap 7: Schrijf .env
        with open(env_path, 'w') as f:
            f.write(f'CLIENT_ID={client_id}\n')
            f.write(f'CLIENT_SECRET={client_secret}\n')
            f.write(f'CSS_BASE_URL={css_base}\n')
            f.write(f'SOLID_POD_URL={pod_url}\n')
            f.write(f'WEBID={webid}\n')
            f.write(f'CSS_EMAIL={email}\n')
            f.write(f'CSS_PASSWORD={password}\n')

        # Herlaad .env en update globale variabelen
        load_dotenv(env_path, override=True)
        CLIENT_ID = os.getenv('CLIENT_ID')
        CLIENT_SECRET = os.getenv('CLIENT_SECRET')
        CSS_BASE_URL = os.getenv('CSS_BASE_URL', 'http://127.0.0.1:3000')
        SOLID_POD_URL = os.getenv('SOLID_POD_URL', f'{css_base}/{pod_name}/')
        WEBID = os.getenv('WEBID', f'{css_base}/{pod_name}/profile/card#me')
        OWNER_WEBID = WEBID

        print(f"  [DEBUG] CLIENT_ID geladen: {CLIENT_ID[:20]}..." if CLIENT_ID else "  [WARN] CLIENT_ID is None!")
        print(f"  [DEBUG] SOLID_POD_URL: {SOLID_POD_URL}")

        print(f"  [OK] Account aangemaakt")
        print(f"  [OK] Pod: {pod_url}")
        print(f"  [OK] WebID: {webid}")
        print(f"  [OK] Credentials opgeslagen in .env")

        return True

    except Exception as e:
        print(f"  [FOUT] Setup mislukt: {e}")
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
    }


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
    if folder_path:
        container_url = SOLID_POD_URL + folder_path + '/'
    else:
        container_url = SOLID_POD_URL

    try:
        response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
        if response and response.status_code == 200:
            items = parse_container_contents(response.text, container_url)

            # Show welcome page if pod root is empty
            if not folder_path and is_pod_empty(items):
                return render_template('welcome.html', pod_url=SOLID_POD_URL)

            items = sort_items(items, sort_by)
            breadcrumbs = build_breadcrumbs(folder_path)
            parts = [p for p in folder_path.split('/') if p]
            parent_path = '/'.join(parts[:-1]) if parts else None
            move_folders = get_move_folders(folder_path, items)
            # Count stats for dashboard
            file_count = sum(1 for i in items if not i['is_folder'])
            folder_count = sum(1 for i in items if i['is_folder'])
            recent_files = get_recent_files() if not folder_path else []
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
            )
        elif response:
            flash(f'Kon map niet laden: {response.status_code}', 'error')
        else:
            flash('Authenticatie mislukt. Controleer client credentials.', 'error')
    except requests.ConnectionError:
        flash('CSS server niet bereikbaar. Draait hij op poort 3000?', 'error')

    breadcrumbs = build_breadcrumbs(folder_path)
    parts = [p for p in folder_path.split('/') if p]
    parent_path = '/'.join(parts[:-1]) if parts else None
    return render_template('index.html',
        items=[],
        pod_url=SOLID_POD_URL,
        folder_path=folder_path,
        breadcrumbs=breadcrumbs,
        parent_path=parent_path,
        all_folders=get_all_folders(),
        move_folders=get_move_folders(folder_path, []),
        file_count=0,
        folder_count=0,
        recent_files=[],
        default_folders=DEFAULT_FOLDERS,
        current_sort=sort_by,
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
    return redirect_to_folder(folder_path)


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
        try:
            results = search_pod(SOLID_POD_URL, query)
            log_action('search', {'query': query, 'results': len(results)})
        except requests.ConnectionError:
            flash('CSS server niet bereikbaar. Draait hij op poort 3000?', 'error')

    return render_template('search.html',
        query=query,
        results=results,
        pod_url=SOLID_POD_URL,
        all_folders=get_all_folders(),
    )


@app.route('/view/<path:file_path>')
def view_file(file_path):
    """View a file inline in the browser"""
    file_url = SOLID_POD_URL + file_path
    response = pod_request('GET', file_url)

    if not response or response.status_code != 200:
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

    if ext in VIEWABLE_TYPES:
        mime = VIEWABLE_TYPES[ext]
        print(f"[view] {filename} → inline, Content-Type: {mime}")
        resp = Response(response.content)
        resp.headers['Content-Type'] = mime
        resp.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        return resp

    print(f"[view] {filename} → attachment")
    resp = Response(response.content)
    resp.headers['Content-Type'] = response.headers.get('Content-Type', 'application/octet-stream')
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


@app.route('/download/<path:file_path>')
def download_file(file_path):
    """Force download a file from the pod"""
    file_url = SOLID_POD_URL + file_path
    response = pod_request('GET', file_url)

    if not response or response.status_code != 200:
        flash('Bestand kon niet worden gedownload', 'error')
        return redirect(url_for('index'))

    content_type = response.headers.get('Content-Type', 'application/octet-stream')
    filename = file_path.split('/')[-1]

    return Response(
        response.content,
        content_type=content_type,
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


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
    return render_template('shares.html', shares=all_shares)


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
    stats = get_storage_stats()
    stats['total_size_formatted'] = format_size(stats['total_size'])
    return render_template('profile.html',
        webid=OWNER_WEBID,
        pod_url=SOLID_POD_URL,
        stats=stats,
    )


@app.route('/settings')
def settings():
    """Show settings page"""
    return render_template('settings.html')


@app.route('/settings/export', methods=['POST'])
def export_backup():
    """Export entire pod as ZIP"""
    buffer = io.BytesIO()

    def add_to_zip(zf, container_url, path='', depth=0, max_depth=5):
        if depth >= max_depth:
            return
        response = pod_request('GET', container_url, headers={'Accept': 'text/turtle'})
        if not response or response.status_code != 200:
            return
        items = parse_container_contents(response.text, container_url)
        for item in items:
            if item['is_folder']:
                sub_path = path + item['name'] + '/'
                add_to_zip(zf, item['url'], sub_path, depth + 1, max_depth)
            else:
                file_path = path + item['name']
                file_response = pod_request('GET', item['url'])
                if file_response and file_response.status_code == 200:
                    zf.writestr(file_path, file_response.content)

    try:
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            add_to_zip(zf, SOLID_POD_URL)
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
