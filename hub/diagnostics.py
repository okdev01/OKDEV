"""Small, local-only checks. Reports never include credentials or raw logs."""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import library


def collect():
    from config import APP_VERSION
    checks = []

    def add(name, status, detail):
        checks.append({'name': name, 'status': status, 'detail': detail})

    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    for name, files in [
        ('Mod araçları', ['injection/tools/mod-tools.exe', 'injection/tools/cslol-dll.dll']),
        ('LTK dosyaları', ['injection/tools/ltk_patcher_host.exe', 'injection/tools/ltk_patcher_dll.dll']),
        ('İstemci bileşenleri', ['Pengu Loader/Pengu Loader.exe', 'Pengu Loader/core.dll']),
        ('Oyun rehberi bileşenleri', ['hub/web/guide.js', 'Pengu Loader/plugins/OKDEV-Guide/index.js']),
    ]:
        missing = [Path(f).name for f in files if not (base / f).is_file()]
        add(name, 'warning' if missing else 'ok',
            'Eksik: ' + ', '.join(missing) if missing else 'Gerekli dosyalar mevcut. Oyun içi uyumluluk ayrıca kontrol edilmelidir.')

    for filename, label in [('installed.json', 'Mod kayıtları'), ('settings.json', 'Tercihler'), ('profiles.json', 'Mod profilleri'), ('catalog.json', 'Katalog önbelleği')]:
        path = library.root() / filename
        if not path.exists():
            add(label, 'info', 'Henüz oluşturulmadı.')
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError()
            if filename == 'installed.json':
                library.installed(strict=True)
            elif filename == 'settings.json':
                library.settings(strict=True)
                from . import preferences
                if any(key in value and not preferences.valid(key, value[key]) for key in preferences.DEFAULTS):
                    raise ValueError()
            elif filename == 'profiles.json':
                from .profiles import list_profiles
                list_profiles(strict=True)
            elif filename == 'catalog.json':
                library.validate_catalog(value)
            add(label, 'ok', 'Kayıt dosyası okunabiliyor.')
        except (OSError, ValueError):
            add(label, 'warning', 'Dosya okunamadı veya biçimi geçersiz. Özgün dosya korunuyor; silmeden önce yedekleyin.')
    items = library.installed()
    from .transactions import status as transaction_status
    pending = transaction_status()['pending']
    add('Yarım kalan işlemler', 'ok' if pending == 0 else 'warning',
        'Tamamlanmayı bekleyen mod işlemi yok.' if pending == 0 else 'Yarım kalmış işlem kayıtları bulundu. Kurtarmayı dene; dosyaların üzerine yazılmaz.')
    missing = [m['name'] for m in items.values() if not library.mod_folder(m).is_dir()]
    add('Yüklü mod dosyaları', 'warning' if missing else 'ok',
        'Yeniden içe aktarılması gerekenler: ' + ', '.join(missing) if missing else f'{len(items)} kayıt kontrol edildi.')
    try:
        free = shutil.disk_usage(library.root()).free / 1024**3
        add('Boş disk alanı', 'warning' if free < 2 else 'ok', f'{free:.1f} GB boş alan.')
    except OSError:
        add('Boş disk alanı', 'warning', 'Disk bilgisi okunamadı.')
    from . import preferences, companion
    prefs, guide_status = preferences.get(), companion.status()
    if not prefs['mobalytics_enabled']:
        add('Mobalytics rehberi', 'info', 'Kapalı. Oyun rehberi sayfasından istediğin zaman etkinleştirebilirsin.')
    elif guide_status.get('running'):
        add('Mobalytics rehberi', 'ok' if guide_status.get('hotkey_ok') else 'warning',
            'Rehber çalışıyor. Kısayol: ' + prefs['mobalytics_hotkey'] if guide_status.get('hotkey_ok') else
            'Kısayol kullanılamıyor. Oyun rehberi sayfasından farklı bir kısayol seç.')
    else:
        add('Mobalytics rehberi', 'info', 'Etkin; rehber penceresi henüz hazır değil. Devam ederse özelliği kapatıp yeniden aç.')
    return {'version': APP_VERSION, 'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': checks,
            'note': 'Yerel dosya kontrolüdür; ağ bağlantısı veya oyun içi uyumluluk testi değildir.'}
