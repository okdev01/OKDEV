#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Party Storage
Keeps each account's party key across sessions, so the token (and room)
friends already have keeps working after OKDEV restarts.
"""

import json
import secrets
import threading
from pathlib import Path

from utils.core.logging import get_logger
from utils.core.paths import get_user_data_dir

log = get_logger()

PARTY_KEYS_FILE = "party_keys.json"
KEY_SIZE = 32
_session_lock = threading.RLock()


def _read_sessions():
    path = get_user_data_dir() / 'party_sessions.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_party_session(summoner_id: int, relay_url: str) -> dict:
    with _session_lock:
        value = _read_sessions().get(f'{relay_url.rstrip("/")}|{summoner_id}', {})
        return value if isinstance(value, dict) else {}


def save_party_session(summoner_id: int, relay_url: str, session: dict) -> None:
    from utils.core.atomic_file import atomic_write
    with _session_lock:
        data = _read_sessions()
        data[f'{relay_url.rstrip("/")}|{summoner_id}'] = session
        path = get_user_data_dir() / 'party_sessions.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with atomic_write(path, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
        except OSError as exc:
            log.warning('[PARTY] Could not remember party: %s', exc)


def _keys_path() -> Path:
    return get_user_data_dir() / PARTY_KEYS_FILE


def load_party_key(summoner_id: int) -> bytes:
    """Return this account's party key, creating and saving one if needed."""
    path = _keys_path()
    keys = {}
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                keys = loaded
    except (OSError, ValueError) as e:
        log.debug(f"[PARTY] Could not read party keys: {e}")

    stored = keys.get(str(summoner_id))
    if isinstance(stored, str):
        try:
            key = bytes.fromhex(stored)
            if len(key) == KEY_SIZE:
                return key
        except ValueError:
            pass

    key = secrets.token_bytes(KEY_SIZE)
    keys[str(summoner_id)] = key.hex()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(keys, indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as e:
        # Still usable for this session; the token just changes next time
        log.warning(f"[PARTY] Could not save party key: {e}")
    return key
