"""
Robust session manager using:
  1. Module-level global dict (primary — same warm Vercel instance)
  2. /tmp file storage (secondary — warm instance restart)
  3. /tmp PDF bytes cache (so test PDF bytes survive across invocations)
"""
import json
import os
import time

SESSION_TTL = 3600  # 1 hour
PDF_DIR = '/tmp/tg_pdfs'
SESSION_DIR = '/tmp/tg_sessions'

# Primary in-memory store — persists across warm Vercel invocations
_MEM: dict = {}


def _ensure_dirs():
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(SESSION_DIR, exist_ok=True)


# ── Session CRUD ──────────────────────────────────────────────────────────────

def get_session(user_id: int) -> dict:
    _ensure_dirs()
    # 1. Try global dict
    if user_id in _MEM:
        d = _MEM[user_id]
        if time.time() - d.get('_ts', 0) <= SESSION_TTL:
            return dict(d)
        del _MEM[user_id]

    # 2. Try /tmp file
    path = os.path.join(SESSION_DIR, f'{user_id}.json')
    if os.path.exists(path):
        try:
            with open(path) as f:
                d = json.load(f)
            if time.time() - d.get('_ts', 0) <= SESSION_TTL:
                _MEM[user_id] = d  # repopulate memory
                return dict(d)
            os.remove(path)
        except Exception:
            pass
    return {}


def set_session(user_id: int, data: dict):
    _ensure_dirs()
    data['_ts'] = time.time()
    _MEM[user_id] = dict(data)
    try:
        path = os.path.join(SESSION_DIR, f'{user_id}.json')
        with open(path, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def clear_session(user_id: int):
    _MEM.pop(user_id, None)
    path = os.path.join(SESSION_DIR, f'{user_id}.json')
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass
    # Also clear cached PDFs
    for role in ('test', 'sol'):
        p = os.path.join(PDF_DIR, f'{user_id}_{role}.pdf')
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


# ── PDF bytes cache ───────────────────────────────────────────────────────────

def save_pdf(user_id: int, role: str, pdf_bytes: bytes):
    """Save PDF bytes to /tmp so they survive across warm invocations."""
    _ensure_dirs()
    path = os.path.join(PDF_DIR, f'{user_id}_{role}.pdf')
    with open(path, 'wb') as f:
        f.write(pdf_bytes)


def load_pdf(user_id: int, role: str) -> bytes | None:
    """Load cached PDF bytes, or None if not found."""
    path = os.path.join(PDF_DIR, f'{user_id}_{role}.pdf')
    if os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                return f.read()
        except Exception:
            pass
    return None
