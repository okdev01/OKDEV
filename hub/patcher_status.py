"""Read local patcher compatibility without networking or starting the game."""
import sys
from datetime import datetime, timezone
from pathlib import Path

from injection.tools.patcher import check_ltk_patcher


def collect():
    from injection.config.config_manager import ConfigManager
    from config import GAME_EXECUTABLE_NAMES
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    game_path = ConfigManager().load_league_path()
    game = None
    if game_path:
        game = next((Path(game_path) / name for name in GAME_EXECUTABLE_NAMES
                     if (Path(game_path) / name).is_file()), None)
    from okdev_ltk_delivery import resolve_patcher_dir
    status = check_ltk_patcher(resolve_patcher_dir(base / 'injection/tools', game), game)
    def date(value):
        return datetime.fromtimestamp(value, timezone.utc).strftime('%d.%m.%Y') if value is not None else None
    reason = ('missing' if status.missing else 'invalid' if status.eol is None else
              'unknown_game' if status.game_build is None else 'expired' if status.expired else 'ready')
    messages = {
        'missing': 'LTK dosyaları eksik. Skin uygulaması hazır değil; kütüphane ve profiller kullanılabilir.',
        'invalid': 'LTK uyumluluğu doğrulanamadı. Skin uygulaması hazır değil; kütüphane ve profiller kullanılabilir.',
        'unknown_game': 'Oyun derlemesi okunamadı. Oyun yolunu kontrol et; skin uyumluluğu henüz doğrulanmadı.',
        'expired': f"LTK, {date(status.eol)} tarihine kadar olan oyun derlemelerini destekliyor; "
                   f"oyunun derlemesi {date(status.game_build)}. Skin uygulaması hazır değil. "
                   'Kütüphane ve profiller kullanılabilir. Uyumlu LTK yayımlandığında OKDEV’i yeniden aç.',
        'ready': 'LTK dosyaları mevcut ve oyun derlemesi destek sınırının içinde.',
    }
    return {'ready': reason == 'ready', 'reason': reason, 'message': messages[reason],
            'eol': status.eol, 'game_build': status.game_build}
