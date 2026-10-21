"""Repair user-local LTK from an unmodified official release, never our CDN."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

import requests

from injection.tools.patcher import check_ltk_patcher, read_game_build
from utils.core.atomic_file import atomic_write

API = 'https://api.github.com/repos/LeagueToolkit/ltk-manager/releases/latest'
NAMES = ('ltk_patcher_host.exe', 'ltk_patcher_dll.dll')
EXTRACTOR_HASHES = {
    '7z.exe': '95fff19b73eff77c87c0d7bd32822e43fb90dd2932459f962eb532d8dfb6ba53',
    '7z.dll': '899cd73d7fc60e1c1c35c7de0f5bed3dc69bfe2cecbd48014d868a347970a0b1',
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def release_asset(release):
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('Kararlı LTK sürümü bulunamadı.')
    tag = release.get('tag_name', '')
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag):
        raise ValueError('LTK sürüm bilgisi doğrulanamadı.')
    name = f'LTK.Manager_{tag[1:]}_x64-setup.exe'
    asset = next((a for a in release.get('assets', []) if a.get('name') == name), None)
    if not asset or asset.get('browser_download_url') != f'https://github.com/LeagueToolkit/ltk-manager/releases/download/{tag}/{name}':
        raise ValueError('Resmî LTK paketi bulunamadı.')
    if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', asset.get('digest') or ''):
        raise ValueError('LTK paketinin SHA-256 bilgisi bulunamadı.')
    if not 0 < asset.get('size', 0) <= 100 * 1024 * 1024:
        raise ValueError('LTK paket boyutu geçersiz.')
    return asset


def download_official(destination, status):
    with requests.get(API, timeout=(10, 30), headers={'User-Agent': 'OKDEV-LTK-Updater'}) as response:
        response.raise_for_status()
        asset = release_asset(response.json())
    status('Güncel LTK resmî kaynaktan indiriliyor…')
    received = 0
    with requests.get(asset['browser_download_url'], stream=True, timeout=(10, 30)) as response:
        response.raise_for_status()
        if urlparse(response.url).scheme != 'https':
            raise ValueError('Güvensiz indirme adresi.')
        with destination.open('wb') as stream:
            for chunk in response.iter_content(256 * 1024):
                received += len(chunk)
                if received > asset['size']:
                    raise ValueError('LTK paket boyutu uyuşmuyor.')
                stream.write(chunk)
    if received != asset['size'] or digest(destination) != asset['digest'].split(':')[1].lower():
        raise ValueError('LTK paketi doğrulanamadı; mevcut dosyalar korunuyor.')
    return asset


def extract_pair(installer, output):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets/7zip'
    for name, expected in EXTRACTOR_HASHES.items():
        if digest(base / name) != expected:
            raise ValueError('Arşiv aracı doğrulanamadı. OKDEV kurulumunu onarın.')
    subprocess.run([str(base/'7z.exe'), 'x', str(installer), f'-o{output}',
                    '-ir!ltk_patcher*', '-y'], check=True, timeout=90,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    # Only the exact pair at the archive root is accepted; never run the installer.
    for name in NAMES:
        p = output / name
        if not p.is_file() or p.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('LTK arşivinde beklenen dosyalar bulunamadı.')
        data = p.read_bytes()
        if data[:2] != b'MZ' or len(data) < 64:
            raise ValueError('Geçersiz LTK dosyası.')
        offset = struct.unpack_from('<I', data, 60)[0]
        if offset + 24 > len(data) or data[offset:offset+6] != b'PE\0\0\x64\x86':
            raise ValueError('LTK dosyası Windows x64 için değil.')


def require_idle():
    import psutil
    blocked = {'league of legends.exe', 'league of legends (tm) client.exe', 'ltk_patcher_host.exe'}
    if any((p.info.get('name') or '').lower() in blocked for p in psutil.process_iter(['name'])):
        raise RuntimeError('LTK güncellemesi için açık maçı ve LTK patcher işlemini kapatın.')


def recover_pair(tools):
    journal = tools / '.ltk-update.json'
    if not journal.exists():
        return
    info = json.loads(journal.read_text(encoding='utf-8'))
    backup_name = info.get('backup', '')
    if not re.fullmatch(r'ltk-backup-[0-9a-f]{32}', backup_name):
        raise ValueError('LTK kurtarma kaydı geçersiz; dosyalar korunuyor.')
    backup = tools / backup_name
    for name in NAMES:
        if info['old'].get(name):
            if digest(backup/name) != info['old'][name]:
                raise ValueError('LTK yedeği doğrulanamadı.')
    for name in NAMES:
        if info['old'].get(name):
            with atomic_write(tools/name, 'wb') as stream:
                stream.write((backup/name).read_bytes())
        else:
            (tools/name).unlink(missing_ok=True)
    journal.unlink()


def install_pair(source, tools, game, asset):
    import uuid
    require_idle()
    status = check_ltk_patcher(source, game)
    if status.missing or status.eol is None or status.game_build is None or status.expired:
        raise ValueError('En yeni resmî LTK bu oyun derlemesini desteklemiyor. Dosyalar değiştirilmedi.')
    backup = tools / ('ltk-backup-' + uuid.uuid4().hex)
    backup.mkdir()
    old = {}
    for name in NAMES:
        old[name] = digest(tools/name) if (tools/name).exists() else None
        if old[name]:
            shutil.copy2(tools/name, backup/name)
    journal = tools / '.ltk-update.json'
    with atomic_write(journal) as stream:
        json.dump({'backup': backup.name, 'old': old, 'source': asset}, stream)
    try:
        for name in NAMES:
            with atomic_write(tools/name, 'wb') as stream:
                stream.write((source/name).read_bytes())
        for name in NAMES:
            if digest(tools/name) != digest(source/name):
                raise ValueError('LTK kopyalama doğrulaması başarısız.')
        journal.unlink()  # commit; backups remain available
    except BaseException:
        recover_pair(tools)
        raise


def ensure_patcher(tools, game, status=lambda text: None):
    """Healthy installs stay offline. Serialize recovery, download and pair swap."""
    import msvcrt
    tools, game = Path(tools), Path(game)
    if not tools.is_dir() or any(p.is_symlink() or p.is_junction() for p in (tools, tools.parent, tools.parents[1])):
        raise ValueError('Geçerli OKDEV araç klasörü bulunamadı.')
    # Shared with OKDEV's installation updater to prevent directory replacement.
    from okdev_install_transaction import installation_lock
    install = tools.parents[2] if tools.parents[1].name == '_internal' else tools.parents[1]
    with installation_lock(install), (tools/'.ltk-update.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('Başka bir LTK güncellemesi çalışıyor.') from None
        try:
            if (tools/'.ltk-update.json').exists():
                require_idle()
                recover_pair(tools)
            current = check_ltk_patcher(tools, game)
            if not current.missing and current.eol is not None and not current.expired:
                return False
            if read_game_build(game) is None:
                raise ValueError('Oyun derlemesi okunamadı. League Game klasörünü kontrol edin.')
            require_idle()
            with tempfile.TemporaryDirectory(prefix='okdev-ltk-') as temp:
                temp = Path(temp)
                asset = download_official(temp/'ltk-setup.exe', status)
                extract_pair(temp/'ltk-setup.exe', temp/'pair')
                status('LTK doğrulanıyor ve yedekli güncelleniyor…')
                install_pair(temp/'pair', tools, game, asset)
            status('LTK güncellendi.')
            return True
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def self_check(report, old_pair, game):
    """Exercise bundled code and extractor without touching the real installation."""
    with tempfile.TemporaryDirectory(prefix='okdev-ltk-check-') as temp:
        tools = Path(temp)/'app/_internal/injection/tools'
        tools.mkdir(parents=True)
        for name in NAMES:
            shutil.copy2(Path(old_pair)/name, tools/name)
        before = check_ltk_patcher(tools, Path(game))
        assert before.expired, 'Self-check requires an expired fixture'
        assert ensure_patcher(tools, Path(game))
        after = check_ltk_patcher(tools, Path(game))
        assert not after.missing and after.eol is not None and not after.expired
        assert not ensure_patcher(tools, Path(game))
        Path(report).write_text(json.dumps({'ok': True, 'old_eol': before.eol,
            'new_eol': after.eol, 'game_build': after.game_build,
            'backups': len(list(tools.glob('ltk-backup-*')))}), encoding='utf-8')
    return 0
