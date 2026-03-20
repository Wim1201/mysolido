import os
import json
import secrets
import hashlib
from datetime import datetime, timedelta

SHARE_LINKS_FILE = '.mysolido/share_links.json'


def get_share_links_path():
    """Pad naar het share_links.json bestand"""
    from app import get_pod_data_path
    pod_path = get_pod_data_path()
    return os.path.join(pod_path, SHARE_LINKS_FILE)


def load_share_links():
    """Laad alle deellinks uit het JSON-bestand"""
    path = get_share_links_path()
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        data = json.load(f)
    return data.get('links', [])


def save_share_links(links):
    """Sla deellinks op naar het JSON-bestand"""
    path = get_share_links_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump({'links': links}, f, indent=2, default=str)


def generate_token():
    """Genereer een cryptografisch veilig token"""
    return secrets.token_urlsafe(32)


def hash_password(password):
    """Hash een wachtwoord met SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def create_share_link(file_path, file_name, expires_days=7, password=None):
    """Maak een nieuwe deellink aan"""
    links = load_share_links()

    token = generate_token()
    link_id = secrets.token_urlsafe(8)

    expires_at = None
    if expires_days and expires_days > 0:
        expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()

    link = {
        'id': link_id,
        'token': token,
        'file_path': file_path,
        'file_name': file_name,
        'created_at': datetime.now().isoformat(),
        'expires_at': expires_at,
        'password_hash': hash_password(password) if password else None,
        'active': True,
        'downloads': 0
    }

    links.append(link)
    save_share_links(links)
    return link


def get_share_link(token):
    """Haal een deellink op via token, check geldigheid"""
    links = load_share_links()
    for link in links:
        if link['token'] == token and link['active']:
            if link['expires_at']:
                if datetime.fromisoformat(link['expires_at']) < datetime.now():
                    return None
            return link
    return None


def deactivate_share_link(link_id):
    """Deactiveer een deellink"""
    links = load_share_links()
    for link in links:
        if link['id'] == link_id:
            link['active'] = False
            save_share_links(links)
            return True
    return False


def get_active_share_links():
    """Haal alle actieve, niet-verlopen deellinks op"""
    links = load_share_links()
    active = []
    now = datetime.now()
    for link in links:
        if link['active']:
            if link['expires_at'] and datetime.fromisoformat(link['expires_at']) < now:
                continue
            active.append(link)
    return active


def increment_download_count(token):
    """Verhoog de download-teller"""
    links = load_share_links()
    for link in links:
        if link['token'] == token:
            link['downloads'] = link.get('downloads', 0) + 1
            save_share_links(links)
            return
