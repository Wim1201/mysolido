import json
from datetime import datetime

AUDIT_LOG_FILE = 'audit_log.json'


def log_action(action, details):
    """Log an action to the audit log"""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'details': details
    }

    try:
        with open(AUDIT_LOG_FILE, 'r', encoding='utf-8') as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log = []

    log.insert(0, entry)  # Newest first

    # Limit to 1000 entries
    log = log[:1000]

    with open(AUDIT_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def get_audit_log(action_filter=None, limit=100):
    """Read the audit log, optionally filtered by action type"""
    try:
        with open(AUDIT_LOG_FILE, 'r', encoding='utf-8') as f:
            log = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    if action_filter:
        log = [entry for entry in log if entry['action'] == action_filter]

    return log[:limit]
