"""Use the official Manager's signed delivery cache; never impersonate its API client.

The official Manager registers and downloads its own signed manifest and DLL.
OKDEV independently verifies them and runs the host at ordinary user integrity.
No service credentials or third-party binaries are included in OKDEV releases.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from packaging.specifiers import SpecifierSet

from injection.tools.patcher import read_dll_eol, read_game_build
from utils.core.atomic_file import atomic_write

PUBLIC_KEY = 'RWSk74swcHfkZfLblm3iSk9RLVHJ1xjtqn/zySIPaCBM1hecnlFy1Bxi'
# Protocol-3 host from the SHA-256-verified official 1.32.0 release. A protocol
# change requires an OKDEV update, rather than running an untested executable.
HOST_SHA256 = '27de1bfdbf37129e42c12b18cc7b4f75c15d39bcd7afefe65c4c33d0e99fe856'
HOST_MANAGER_VERSION = '1.32.0'
HOST = 'ltk_patcher_host.exe'
DLL = 'ltk_patcher_dll.dll'


def _read_json(path, limit=1024 * 1024):
    if path.stat().st_size > limit:
        raise ValueError('LTK kayıt boyutu geçersiz.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('LTK kayıt biçimi geçersiz.')
    return value


def verify_manifest(envelope):
    """Verify both minisign signatures, including the channel/sequence comment."""
    raw = base64.b64decode(envelope['manifest'], validate=True)
    if len(raw) > 256 * 1024:
        raise ValueError('LTK manifest boyutu geçersiz.')
    lines = envelope['signature'].splitlines()
    if len(lines) != 4 or not lines[0].startswith('untrusted comment: ') or not lines[2].startswith('trusted comment: '):
        raise ValueError('LTK imza biçimi geçersiz.')
    key = base64.b64decode(PUBLIC_KEY, validate=True)
    signature = base64.b64decode(lines[1], validate=True)
    global_sig = base64.b64decode(lines[3], validate=True)
    if len(key) != 42 or key[:2] != b'Ed' or len(signature) != 74 or signature[:2] not in (b'Ed', b'ED') or signature[2:10] != key[2:10]:
        raise ValueError('LTK imza anahtarı geçersiz.')
    verifier = VerifyKey(key[10:])
    verifier.verify(hashlib.blake2b(raw).digest() if signature[:2] == b'ED' else raw, signature[10:])
    comment = lines[2][len('trusted comment: '):]
    verifier.verify(signature[10:] + comment.encode('utf-8'), global_sig)
    manifest = json.loads(raw)
    release = manifest['release']
    if (manifest['schema'] != 1 or manifest['channel'] not in ('stable', 'beta')
            or type(manifest['sequence']) is not int or manifest['sequence'] <= 0
            or not re.fullmatch(r'ltk_patcher-[1-9][0-9]*', release['version'])
            or not re.fullmatch(r'[0-9a-f]{64}', release['digest'])
            or type(release['size']) is not int or not 0 < release['size'] <= 32 * 1024 * 1024
            or type(release['eol']) is not int or not 0 < release['eol'] <= 0xFFFFFFFF
            or comment != f"{manifest['channel']} {manifest['sequence']} {release['version']}"
            or not isinstance(manifest['revoked'], list)
            or not all(isinstance(x, str) and re.fullmatch(r'[0-9a-f]{64}', x) for x in manifest['revoked'])):
        raise ValueError('LTK manifest alanları geçersiz.')
    return manifest


def manager_dir():
    return Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'LTK Manager'


def delivery_root():
    base = Path(os.environ['APPDATA']) / 'dev.leaguetoolkit.manager'
    try:
        settings = _read_json(base / 'settings.json')
        custom = settings.get('modStoragePath')
        if isinstance(custom, str) and Path(custom).is_absolute():
            return Path(custom) / 'patcher'
    except (OSError, ValueError):
        pass
    return base / 'patcher'


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def runtime_root():
    from utils.core.paths import get_user_data_dir
    return get_user_data_dir() / 'ltk-runtime'


def select_cached(game=None, stage=False):
    """Only a signed, non-revoked, compatible stable release can be selected."""
    try:
        root = delivery_root()
        state = _read_json(root / 'delivery.json')
        manifests = {}
        for channel, entry in state.get('channels', {}).items():
            manifest = verify_manifest(entry['envelope'])
            if manifest['channel'] != channel:
                raise ValueError('LTK kanal bilgisi uyuşmuyor.')
            manifests[channel] = manifest
        manifest = manifests['stable']
        release = manifest['release']
        revoked = {digest for m in manifests.values() for digest in m['revoked']}
        if (release['digest'] in revoked or release['protocol'] != 3
                or not release['managers'].strip().startswith('>=')
                or HOST_MANAGER_VERSION not in SpecifierSet(release['managers'])):
            return None
        build = read_game_build(Path(game)) if game else None
        if game and (build is None or build > release['eol']):
            return None
        dll = root / release['digest'] / DLL
        host = manager_dir() / HOST
        if (not dll.is_file() or dll.stat().st_size != release['size'] or _sha(dll) != release['digest']
                or read_dll_eol(dll) != release['eol'] or not host.is_file() or _sha(host) != HOST_SHA256):
            return None
        target = runtime_root() / release['digest']
        if stage:
            target.mkdir(parents=True, exist_ok=True)
            # Reject links before writing and again before executing.
            if any(p.is_symlink() or p.is_junction() for p in (target, target.parent)):
                raise ValueError('LTK çalışma klasörü bağlantı olamaz.')
            for source, name, expected in ((dll, DLL, release['digest']), (host, HOST, HOST_SHA256)):
                dest = target / name
                if not dest.is_file() or _sha(dest) != expected:
                    with atomic_write(dest, 'wb') as stream:
                        stream.write(source.read_bytes())
        if any(p.is_symlink() or p.is_junction() for p in (target, target.parent, target / HOST, target / DLL)):
            return None
        if _sha(target / HOST) != HOST_SHA256 or _sha(target / DLL) != release['digest']:
            return None
        return target
    except (OSError, ValueError, KeyError, TypeError, AttributeError, BadSignatureError):
        return None


def resolve_patcher_dir(fallback, game=None):
    from okdev_ltk_compat import resolve_verified
    return resolve_verified(game) or select_cached(game) or Path(fallback)


def _hide_owned_windows(pid):
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    @callback
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            user.ShowWindow(hwnd, 0)
        return True
    user.EnumWindows(visit, 0)


def sync_official(game, installer=None, status=lambda text: None, timeout=90):
    """Let the unmodified official client obtain its own authorized delivery.

    No token is copied out of its state or sent by OKDEV. Only the public signed
    envelope and matching DLL are consumed. Existing user-owned Manager sessions
    are never terminated; only a helper process created here is closed.
    """
    cached = select_cached(game, stage=True)
    if cached:
        return cached
    manager = manager_dir() / 'ltk-manager.exe'
    if installer is not None:
        status('LoL skin bileşeni resmî paketle hazırlanıyor…')
        # The caller has verified this complete official archive before execution.
        subprocess.run([str(installer), '/S'], check=True, timeout=120,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    if not manager.is_file():
        return None
    # A host of a different protocol must not be used by this release.
    if not (manager_dir() / HOST).is_file() or _sha(manager_dir() / HOST) != HOST_SHA256:
        return None
    import psutil
    existing = any((p.info.get('name') or '').lower() == 'ltk-manager.exe'
                   for p in psutil.process_iter(['name']))
    child = None
    if not existing:
        from utils.system.user_process import popen
        child = popen([str(manager), '--shell-relaunched'], cwd=manager_dir())
    status('LoL skin bileşeni güncel oyun için eşitleniyor…')
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if child:
                _hide_owned_windows(child.pid)
            cached = select_cached(game, stage=True)
            if cached:
                return cached
            if child and child.poll() is not None:
                break
            time.sleep(.5)
        return None
    finally:
        if child:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
            child.stdin.close()
            child.stdout.close()
