import json
from datetime import datetime

SHARES_FILE = 'shares.json'


def load_shares():
    """Load all shares from shares.json"""
    try:
        with open(SHARES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_shares(shares):
    """Save shares to shares.json"""
    with open(SHARES_FILE, 'w', encoding='utf-8') as f:
        json.dump(shares, f, indent=2, ensure_ascii=False)


def add_share(resource_url, resource_path, webid, modes, expires=None):
    """Add a share entry. webid='public' for public access."""
    shares = load_shares()
    shares.append({
        'resource_url': resource_url,
        'resource_path': resource_path,
        'webid': webid,
        'modes': modes,
        'expires': expires,
        'created': datetime.now().isoformat(),
    })
    save_shares(shares)


def remove_share(resource_url, webid):
    """Remove a specific share entry"""
    shares = load_shares()
    shares = [s for s in shares if not (s['resource_url'] == resource_url and s['webid'] == webid)]
    save_shares(shares)


def get_shares_for_resource(resource_url):
    """Get all active (non-expired) shares for a specific resource"""
    shares = load_shares()
    now = datetime.now().isoformat()
    return [
        s for s in shares
        if s['resource_url'] == resource_url
        and (not s.get('expires') or s['expires'] > now)
    ]


def get_all_shares():
    """Get all shares"""
    return load_shares()


def check_expired_shares():
    """Find and return expired shares, then remove them from the file"""
    shares = load_shares()
    now = datetime.now().isoformat()

    expired = [s for s in shares if s.get('expires') and s['expires'] <= now]
    active = [s for s in shares if not s.get('expires') or s['expires'] > now]

    if expired:
        save_shares(active)

    return expired
