import json
import os
import uuid
from datetime import datetime

NOTIFICATIONS_FILE = 'notifications.json'
MAX_NOTIFICATIONS = 200


def load_notifications():
    """Load all notifications from JSON file"""
    if not os.path.exists(NOTIFICATIONS_FILE):
        return []
    with open(NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_notifications(items):
    """Save notifications to JSON file"""
    with open(NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_notification(ntype, message, details=None):
    """Add a notification entry"""
    items = load_notifications()
    entry = {
        'id': uuid.uuid4().hex[:12],
        'type': ntype,
        'message': message,
        'details': details or {},
        'read': False,
        'created_at': datetime.now().isoformat(),
    }
    items.insert(0, entry)
    # Keep max notifications
    if len(items) > MAX_NOTIFICATIONS:
        items = items[:MAX_NOTIFICATIONS]
    save_notifications(items)
    return entry


def get_all_notifications(limit=50):
    """Get notifications, newest first"""
    items = load_notifications()
    items.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return items[:limit]


def get_unread_count():
    """Count unread notifications"""
    items = load_notifications()
    return sum(1 for item in items if not item.get('read', True))


def mark_as_read(notification_id):
    """Mark a single notification as read"""
    items = load_notifications()
    for item in items:
        if item['id'] == notification_id:
            item['read'] = True
            break
    save_notifications(items)


def mark_all_read():
    """Mark all notifications as read"""
    items = load_notifications()
    for item in items:
        item['read'] = True
    save_notifications(items)
