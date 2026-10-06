#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create the update package the launcher downloads from a GitHub release

Zips dist/OKDEV (OKDEV.exe and _internal/ at the root of the archive, as the
updater extracts it) into installer/update_package_<version>.zip. Run it on
the signed build, next to the installer.
"""

import re
import json
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "OKDEV"
OUTPUT_DIR = ROOT / "release"
# Downloaded by the launcher from the release on its own (see update_sequence),
# and left out of the installer too
EXCLUDED_NAMES = {"hashes.game.txt", "party_sessions.json", "party_keys.json", "historic.json", "analytics_install_id.txt"}


def app_version() -> str:
    """The version in config.py, which must match installer.iss."""
    config = (ROOT / "config.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', config, re.MULTILINE)
    if not match:
        raise SystemExit("APP_VERSION not found in config.py")
    version = match.group(1)
    iss = (ROOT / "installer.iss").read_text(encoding="utf-8")
    iss_match = re.search(r'^#define MyAppVersion "([^"]+)"', iss, re.MULTILINE)
    if not iss_match or iss_match.group(1) != version:
        raise SystemExit(
            f"config.py says {version} but installer.iss says "
            f"{iss_match.group(1) if iss_match else 'nothing'}: bump both"
        )
    return version


def packaged_files():
    for path in sorted(DIST.rglob("*")):
        if (not path.is_file() or path.name.lower() in EXCLUDED_NAMES
                or 'ltk_patcher' in path.name.lower() or path.name.lower() in {'config.ini', 'datastore', 'config', 'okdev-install.json'}
                or path.name.lower().endswith(('.log', '.log.old'))):
            continue
        # A package left in dist/OKDEV by hand isn't part of the build
        if path.parent == DIST and path.suffix.lower() == ".zip":
            continue
        yield path


def create_update_package() -> Path:
    if not (DIST / "OKDEV.exe").is_file():
        raise SystemExit(f"{DIST / 'OKDEV.exe'} not found: build OKDEV first")

    version = app_version()
    OUTPUT_DIR.mkdir(exist_ok=True)
    target = OUTPUT_DIR / f"OKDEV_Update_{version}.zip"
    partial = target.with_suffix(".zip.partial")

    count = 0
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in packaged_files():
            archive.write(path, path.relative_to(DIST).as_posix())
            count += 1
        archive.writestr("okdev-update.json", json.dumps({"app": "OKDEV", "version": version}))
    partial.replace(target)
    with target.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest + "  " + target.name + "\n", encoding="ascii")

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"Update package: {target} ({count} files, {size_mb:.1f} MB)")
    return target


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    create_update_package()
