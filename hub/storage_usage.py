"""Bounded, read-only logical file sizes for the local diagnostics screen."""
import os
import stat
import time

from . import library


def scan(path, *, max_entries=20000, seconds=.4, children_prefix=None):
    """Never follow reparse points; return an explicit lower bound if incomplete.

    The time budget bounds traversal between filesystem calls (an individual
    filesystem call may still block). Sizes are file lengths, not allocated disk
    blocks, and can change while an installation or browser cache is active.
    """
    result = {'bytes': 0, 'files': 0, 'complete': True}
    deadline = time.monotonic() + seconds
    pending = [(path, children_prefix)]
    visited = 0
    while pending:
        if visited >= max_entries or time.monotonic() >= deadline:
            result['complete'] = False
            break
        current, prefix = pending.pop()
        visited += 1
        try:
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
                result['complete'] = False
                continue
            if stat.S_ISREG(metadata.st_mode):
                result['bytes'] += metadata.st_size
                result['files'] += 1
                continue
            if not stat.S_ISDIR(metadata.st_mode):
                result['complete'] = False
                continue
            with os.scandir(current) as entries:
                for entry in entries:
                    if visited + len(pending) >= max_entries or time.monotonic() >= deadline:
                        result['complete'] = False
                        break
                    # Bound even nonmatching siblings when selecting downloads.
                    if prefix is not None and not entry.name.startswith(prefix):
                        visited += 1
                        continue
                    pending.append((current / entry.name, None))
        except FileNotFoundError:
            # An absent category is normal; a disappearing child is a live scan.
            if current != path:
                result['complete'] = False
        except OSError:
            result['complete'] = False
    return result


def collect():
    root = library.root()
    categories = [
        ('mods', 'Mod dosyaları', root.parent / 'mods', None),
        ('backups', 'Yerel yedekler', root / 'removed', None),
        ('covers', 'Kapak görselleri', root / 'covers', None),
        ('downloads', 'Geçici indirmeler', root, 'download-'),
        ('webview', 'Mod Merkezi önbelleği', root / 'webview', None),
        ('guide', 'Rehber önbelleği', root / 'guide-webview', None),
    ]
    return [{'id': identity, 'name': name, **scan(path, children_prefix=prefix)}
            for identity, name, path, prefix in categories]
