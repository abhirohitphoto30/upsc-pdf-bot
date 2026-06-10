"""
Simple file-based session manager using /tmp.
Persists state between warm Vercel function invocations.
"""
import json
import os
import time

SESSION_DIR = '/tmp/tg_sessions'
SESSION_TTL = 3600  # 1 hour


def _ensure_dir():
    os.makedirs(SESSION_DIR, exist_ok=True)


def _session_path(user_id: int) -> str:
    return os.path.join(SESSION_DIR, f'{user_id}.json')


def get_session(user_id: int) -> dict:
    _ensure_dir()
    path = _session_path(user_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if time.time() - data.get('_ts', 0) > SESSION_TTL:
            os.remove(path)
            return {}
        return data
    except Exception:
        return {}


def set_session(user_id: int, data: dict):
    _ensure_dir()
    data['_ts'] = time.time()
    with open(_session_path(user_id), 'w') as f:
        json.dump(data, f)


def clear_session(user_id: int):
    path = _session_path(user_id)
    if os.path.exists(path):
        os.remove(path)


def _cleanup_old_sessions():
    """Remove sessions older than TTL."""
    try:
        for fname in os.listdir(SESSION_DIR):
            path = os.path.join(SESSION_DIR, fname)
            try:
                with open(path) as f:
                    data = json.load(f)
                if time.time() - data.get('_ts', 0) > SESSION_TTL:
                    os.remove(path)
            except Exception:
                pass
    except Exception:
        pass
