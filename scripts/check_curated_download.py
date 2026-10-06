"""Download one pinned original package through the real API into temporary data."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from utils.core import paths
    previous = paths._cached_user_data_dir
    previous_migration = paths._migration_checked
    report = {'ok': False}
    try:
        with tempfile.TemporaryDirectory(prefix='okdev-source-check-') as tmp:
            paths._cached_user_data_dir = Path(tmp)
            paths._migration_checked = True
            from hub import library, sources
            from hub.desktop import Api
            item = min(sources.entries(), key=lambda m: m['download_size'])
            result = Api().download_source(item['id'])
            assert result['ok'], result.get('error')
            installed = library.installed(strict=True)[item['id']]
            assert not installed['enabled'], 'New package must stay disabled'
            for field in ('sha256', 'author', 'license', 'source_url'):
                assert installed[field] == item[field], field
            assert library.mod_folder(installed).is_relative_to(Path(tmp).resolve()), 'Package escaped isolated directory'
            report.update(ok=True, id=item['id'], bytes=item['download_size'], sha256=installed['sha256'],
                scope='Real original-CDN download, archive/hash validation, API import and attribution in isolated data.')
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        paths._cached_user_data_dir = previous
        paths._migration_checked = previous_migration
    (ROOT / 'build/curated-download-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
