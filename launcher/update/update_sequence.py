"""Check the OKDEV release channel, verify the payload, and stage an update."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys
import requests
from config import APP_VERSION, get_config_file_path
from .github_client import GitHubClient
from .update_downloader import UpdateDownloader
from .update_installer import UpdateInstaller


def _parse_semver_like(version):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(version))
    return tuple(map(int, match.groups())) if match else None


def _cmp_version(a, b):
    return None if a is None or b is None else (a > b) - (a < b)


class UpdateSequence:
    def __init__(self):
        self.github_client = GitHubClient()
        self.downloader = UpdateDownloader()
        self.installer = UpdateInstaller()

    def perform_update(self, status_callback, progress_callback, bytes_callback=None,
                       dev_mode=False, confirm_callback=None):
        if dev_mode or not getattr(sys, 'frozen', False):
            status_callback('Güncelleme kontrolü geliştirme modunda atlandı')
            return False
        try:
            return self._perform(status_callback, progress_callback, bytes_callback, confirm_callback)
        except Exception as exc:
            status_callback(f'Güncelleme uygulanamadı; mevcut sürüm açılıyor: {exc}')
            return False

    def _perform(self, status, progress, byte_progress, confirm):
        status('OKDEV güncellemeleri kontrol ediliyor…')
        release = self.github_client.get_latest_release()
        if not release or release.get('draft') or release.get('prerelease'):
            return False
        remote = self.github_client.get_release_version(release)
        parsed = _parse_semver_like(remote)
        if not parsed or parsed <= _parse_semver_like(APP_VERSION):
            return False
        asset = self.github_client.get_zip_asset(release)
        if not asset:
            return False
        import psutil
        if any((p.info.get('name') or '').lower() in {'leagueclientux.exe', 'leagueclientuxrender.exe', 'league of legends.exe'}
               for p in psutil.process_iter(['name'])):
            status('OKDEV güncellemesi hazır; oyun istemcisi kapalıyken uygulanacak')
            return False
        if confirm is None or not confirm(remote, APP_VERSION):
            return False
        root = get_config_file_path().parent/'updates'
        root.mkdir(parents=True, exist_ok=True)
        archive = root/asset['name']
        checksum_asset = next((a for a in release.get('assets', []) if a.get('name') == asset['name']+'.sha256'), None)
        digest = asset.get('digest') or ''
        if re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest):
            expected = digest.split(':')[1].lower()
        elif checksum_asset and self.github_client.is_release_url(checksum_asset.get('browser_download_url', '')):
            response = requests.get(checksum_asset['browser_download_url'], timeout=20)
            response.raise_for_status()
            expected = response.text.split()[0].lower()
            if not re.fullmatch('[0-9a-f]{64}', expected):
                raise ValueError('Geçersiz paket özeti')
        else:
            raise ValueError('Paket doğrulama bilgisi bulunamadı')
        if not self.downloader.download_update(asset['browser_download_url'], archive, status, byte_progress, asset.get('size')):
            return False
        with archive.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            archive.unlink(missing_ok=True)
            raise ValueError('Güncelleme dosyası SHA-256 doğrulamasından geçemedi')
        staging = root/'staging'
        extracted = self.installer.extract_update(archive, staging, progress, status)
        if extracted is None:
            return False
        manifest = json.loads((extracted/'okdev-update.json').read_text(encoding='utf-8'))
        if _parse_semver_like(manifest.get('version')) != parsed:
            raise ValueError('Paket sürümü yayımlanan sürümle eşleşmiyor')
        install = Path(sys.executable).resolve().parent
        params = self.installer.prepare_updater_launch(extracted, install, root, archive, staging, status)
        return bool(params and self.installer.launch_updater(params, install, root, archive, staging, status))
