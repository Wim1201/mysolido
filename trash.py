import json
import os
import uuid
from datetime import datetime, timedelta

TRASH_FILE = 'trash.json'


def load_trash():
    """Load all trash entries from JSON file"""
    if not os.path.exists(TRASH_FILE):
        return []
    with open(TRASH_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_trash(items):
    """Save trash entries to JSON file"""
    with open(TRASH_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def move_to_trash(resource_url, resource_path, filename, original_folder, trash_url):
    """Add an entry to trash.json. Returns the trash entry."""
    items = load_trash()
    entry = {
        'trash_id': uuid.uuid4().hex[:12],
        'filename': filename,
        'original_path': resource_path,
        'original_folder': original_folder,
        'resource_url': resource_url,
        'trash_url': trash_url,
        'deleted_at': datetime.now().isoformat(),
    }
    items.insert(0, entry)
    save_trash(items)
    return entry


def restore_from_trash(trash_id):
    """Remove entry from trash.json by trash_id. Returns the entry or None."""
    items = load_trash()
    for i, item in enumerate(items):
        if item['trash_id'] == trash_id:
            entry = items.pop(i)
            save_trash(items)
            return entry
    return None


def permanent_delete(trash_id):
    """Remove entry from trash.json by trash_id. Returns the entry or None."""
    items = load_trash()
    for i, item in enumerate(items):
        if item['trash_id'] == trash_id:
            entry = items.pop(i)
            save_trash(items)
            return entry
    return None


def get_all_trash():
    """Return all trash entries, sorted newest first"""
    items = load_trash()
    items.sort(key=lambda x: x.get('deleted_at', ''), reverse=True)
    return items


def cleanup_expired(days=30):
    """Find entries older than `days` days, remove from trash.json, return them."""
    items = load_trash()
    cutoff = datetime.now() - timedelta(days=days)
    expired = []
    remaining = []
    for item in items:
        try:
            deleted_at = datetime.fromisoformat(item['deleted_at'])
            if deleted_at < cutoff:
                expired.append(item)
            else:
                remaining.append(item)
        except (KeyError, ValueError):
            remaining.append(item)
    if expired:
        save_trash(remaining)
    return expired
