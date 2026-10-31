"""Prepare a selection without losing the previous staging on ordinary failure."""
from contextlib import contextmanager
from pathlib import Path
import tempfile

from utils.core.junction import is_junction, link_or_extract, safe_remove_entry, staging_name
from utils.core.logging import get_logger


@contextmanager
def prepare_selection(source, mods_dir, cache_dir, *, replace_all, previous_name=None):
    """Caller holds the library lock and commits selection inside this context.

    Preparation and backups live beside, never inside, the active mod directory.
    Rename failures and a failed registry write restore the prior staged entries.
    A failed rollback retains the backup directory for recovery.
    """
    mods_dir = Path(mods_dir).absolute()
    mods_dir.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.selection-', dir=mods_dir.parent))
    prepared = work / 'prepared'
    backup = work / 'backup'
    destination = mods_dir / staging_name(source)
    moved, placed, cleanup = [], False, True
    try:
        link_or_extract(source, prepared, cache_dir=cache_dir, staging_dir=mods_dir)
        if not prepared.exists():
            raise RuntimeError('The mod could not be prepared')
        mods_dir.mkdir(parents=True, exist_ok=True)
        backup.mkdir()
        # Names are compared against actual children; no caller-provided path
        # is used for moving or removing entries outside the staging directory.
        entries = [entry for entry in mods_dir.iterdir()
                   if replace_all or entry.name in (destination.name, previous_name)]
        try:
            for entry in entries:
                saved = backup / entry.name
                entry.rename(saved)
                moved.append((entry, saved))
            prepared.rename(destination)
            placed = True
            yield destination
        except BaseException:
            cleanup = False
            if placed:
                safe_remove_entry(destination, strict=True)
            for entry, saved in reversed(moved):
                if entry.exists() or is_junction(entry):
                    raise OSError('Selection rollback destination is occupied: ' + str(entry))
                saved.rename(entry)
            cleanup = True
            raise
    finally:
        if cleanup:
            # Explicitly unlink junctions before removing their containers.
            # Cleanup failure after commit must not report selection failure.
            try:
                if prepared.exists() or is_junction(prepared):
                    safe_remove_entry(prepared, strict=True)
                if backup.exists():
                    for entry in backup.iterdir():
                        safe_remove_entry(entry, strict=True)
                    backup.rmdir()
                work.rmdir()
            except OSError as exc:
                get_logger().warning('Selection staging cleanup deferred: %s', exc)
        else:
            get_logger().error('Selection rollback incomplete; backups retained at %s', work)
