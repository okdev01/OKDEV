#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Junction Utilities for Windows
Provides directory junctions to avoid copying large mods on every injection.
Falls back to shutil.copytree when junctions are unavailable.
"""

import os
import shutil
import tempfile
import stat
import hashlib
import re
import time
from pathlib import Path
from typing import Union

from utils.core.logging import get_logger
from utils.core.safe_extract import MOD_ARCHIVE_SUFFIXES, extract_mod_archive

log = get_logger()
_cache_sweeps = {}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_junction(path: Union[str, Path]) -> bool:
    """Detect whether *path* is a Windows junction (reparse point).

    Uses ``os.stat`` with ``follow_symlinks=False`` to read
    ``st_file_attributes`` which includes ``FILE_ATTRIBUTE_REPARSE_POINT``.
    Returns ``False`` on non-Windows platforms or if the path doesn't exist.
    """
    path = Path(path)
    try:
        # os.lstat does not follow symlinks/junctions
        st = os.lstat(path)
        attrs = getattr(st, "st_file_attributes", 0)
        # FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def create_junction(source: Path, link: Path) -> bool:
    """Create a Windows directory junction at *link* pointing to *source*.

    Returns ``True`` on success.  Falls back to ``shutil.copytree`` and
    returns ``False`` if the junction cannot be created (non-Windows, missing
    API, etc.).
    """
    source = Path(source).resolve()
    link = Path(link)

    try:
        import _winapi  # type: ignore[import-not-found]
        _winapi.CreateJunction(str(source), str(link))
        log.info(f"[JUNCTION] Created junction: {link} -> {source}")
        return True
    except Exception as exc:
        log.warning(f"[JUNCTION] CreateJunction failed ({exc}), falling back to copytree")
        link.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.copy-', dir=link.parent))
        try:
            shutil.copytree(source, temporary, dirs_exist_ok=True)
            temporary.rename(link)
            log.info(f"[JUNCTION] Fallback copytree: {source} -> {link}")
        finally:
            if temporary.exists():
                safe_remove_entry(temporary, strict=True)
        return False


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------

def safe_remove_entry(path: Union[str, Path], *, strict: bool = False) -> None:
    """Remove *path* safely, handling junctions and regular dirs/files.

    * **Junction / symlink**: removed with ``os.rmdir`` which deletes the
      link itself without following it or touching the target.
    * **Directory**: removed with ``shutil.rmtree(ignore_errors=True)``.
    * **File**: removed with ``os.unlink``.
    """
    path = Path(path)

    if is_junction(path):
        try:
            os.rmdir(path)  # removes junction point only
            log.debug(f"[JUNCTION] Removed junction: {path}")
        except OSError as exc:
            if strict:
                raise
            log.warning(f"[JUNCTION] Failed to remove junction {path}: {exc}")
        return

    if path.is_dir():
        shutil.rmtree(path, ignore_errors=not strict)
        if strict and path.exists():
            raise OSError(f"Could not remove {path}")
        return

    if path.exists():
        try:
            path.unlink()
        except OSError:
            if strict:
                raise
            pass


# ---------------------------------------------------------------------------
# Cache helpers for mod archives (ZIP / fantome / modpkg)
# ---------------------------------------------------------------------------


def staging_name(source: Path, label: str = '') -> str:
    """Distinct storage entries must never share an overlay staging directory."""
    identity = str(Path(source).resolve()).casefold()
    return 'mod-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]

def _get_or_extract_to_cache(
    zip_path: Path,
    folder_name: str,
    cache_dir: Path,
) -> Path:
    """Return a cached extraction of *zip_path* inside *cache_dir*.

    Source identity and revision form an immutable cache key. Different paths
    with equal archive names/timestamps cannot share extracted content, and a
    new revision cannot overwrite a directory used by an existing junction.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    identity = (str(zip_path.resolve()).casefold(), archive_digest(zip_path))
    revision = hashlib.sha256(repr(identity).encode('utf-8')).hexdigest()[:24]
    folder_name = revision
    cached = cache_dir / folder_name

    from hub.locking import settings_lock
    from utils.core.atomic_file import write_text_atomic
    import tempfile
    stamp = cache_dir / f"{folder_name}.mtime"
    source_mtime = repr(identity)
    with settings_lock(cache_dir / (revision + '.lock'), timeout_ms=120000):
        if cached.is_dir() and not is_junction(cached):
            # Directory publication is atomic and the name already includes
            # source path + content hash. Repair old ANSI/corrupt stamps without
            # replacing a directory an active overlay may still reference.
            try:
                valid_stamp = stamp.read_text(encoding='utf-8') == source_mtime
            except (OSError, UnicodeError):
                valid_stamp = False
            if not valid_stamp:
                write_text_atomic(stamp, source_mtime)
            return cached
        temporary = Path(tempfile.mkdtemp(prefix='.extract-', dir=cache_dir))
        try:
            extract_mod_archive(zip_path, temporary)
            if archive_digest(zip_path) != identity[1]:
                raise OSError('Mod archive changed while it was being extracted')
            if cached.exists() or is_junction(cached):
                safe_remove_entry(cached, strict=True)
            temporary.rename(cached)
            write_text_atomic(stamp, source_mtime)
        finally:
            if temporary.exists():
                safe_remove_entry(temporary, strict=True)
    return cached


def archive_digest(path: Path) -> str:
    """Content identity also detects replacements that retain Windows timestamps."""
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prune_extraction_cache(cache_dir: Path, staging_dir: Path, *, protected=(), max_bytes=2 * 1024**3, max_entries=32, max_age=7 * 86400):
    """Remove only generated, unreferenced cache entries. Caller holds cache lock.

    Active junction targets are exempt even when they exceed the quota. Never
    traverse or delete a linked cache directory or an unrelated named folder.
    """
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir() or is_junction(cache_dir):
        return
    base = cache_dir.resolve()
    retained = {Path(p).resolve() for p in protected}
    for staging in {Path(staging_dir), cache_dir.parent / 'mods'}:
        if staging.is_dir():
            for entry in staging.iterdir():
                if is_junction(entry) or entry.is_symlink():
                    retained.add(entry.resolve())
    entries = []
    for entry in cache_dir.iterdir():
        if not re.fullmatch('[a-f0-9]{24}', entry.name) or not entry.is_dir() or is_junction(entry):
            continue
        if entry.resolve() != base / entry.name:
            continue
        size = 0
        for directory, dirs, files in os.walk(entry, followlinks=False):
            dirs[:] = [name for name in dirs if not is_junction(Path(directory) / name)]
            size += sum((Path(directory) / name).lstat().st_size for name in files)
        stamp = entry.with_suffix('.mtime')
        used = stamp.stat().st_mtime if stamp.exists() else entry.stat().st_mtime
        entries.append((used, entry, size, stamp))
    total, count, now = sum(row[2] for row in entries), len(entries), time.time()
    for used, entry, size, stamp in sorted(entries):
        if entry.resolve() in retained:
            continue
        if now - used <= max_age and total <= max_bytes and count <= max_entries:
            continue
        # Recheck the resolved target immediately before recursive removal.
        if is_junction(entry) or entry.resolve() != base / entry.name:
            continue
        safe_remove_entry(entry, strict=True)
        stamp.unlink(missing_ok=True)
        total -= size
        count -= 1


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------

def link_or_extract(
    source: Path,
    dest: Path,
    cache_dir: Path,
) -> None:
    """Place mod content at *dest* using the fastest available method.

    * **Directory source**: create a junction from *dest* -> *source* (zero
      copy).  Falls back to ``shutil.copytree``.
    * **ZIP / fantome / modpkg source**: extract once into *cache_dir*, then junction
      *dest* -> cached directory.  Subsequent calls are instant.
    * **Other file**: plain ``shutil.copy2`` into *dest*.
    """
    source = Path(source)
    dest = Path(dest)

    if source.is_dir():
        create_junction(source, dest)

    elif source.is_file() and source.suffix.lower() in MOD_ARCHIVE_SUFFIXES:
        from hub.locking import settings_lock
        cache_dir.mkdir(parents=True, exist_ok=True)
        with settings_lock(cache_dir / 'cache-state.lock', timeout_ms=120000):
            cached = _get_or_extract_to_cache(source, source.stem, cache_dir)
            create_junction(cached, dest)
            cached.with_suffix('.mtime').touch()
            cache_key = str(cache_dir.resolve())
            if time.monotonic() - _cache_sweeps.get(cache_key, float('-inf')) >= 60:
                try:
                    prune_extraction_cache(cache_dir, dest.parent, protected=[cached])
                except OSError as exc:
                    log.warning(f'[JUNCTION] Cache cleanup deferred: {exc}')
                _cache_sweeps[cache_key] = time.monotonic()

    elif source.is_file():
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest / source.name)
        log.info(f"[JUNCTION] Copied file: {source.name} -> {dest}")

    else:
        raise FileNotFoundError(f'Mod source does not exist: {source}')
