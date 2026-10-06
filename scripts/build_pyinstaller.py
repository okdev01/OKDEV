#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build script for OKDEV using PyInstaller
Fast builds with Windows UI API support
"""

import sys
import subprocess
import shutil
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


MIN_PYTHON = (3, 12)
if sys.version_info < MIN_PYTHON:
    sys.stderr.write(
        f"OKDEV build scripts require Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer.\n"
        "Please re-run using an updated interpreter.\n"
    )
    sys.exit(1)


def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def print_step(step_num, total_steps, description):
    """Print a step description"""
    print(f"\n[Step {step_num}/{total_steps}] {description}")
    print("-" * 70)


def clean_previous_builds():
    """Clean previous build output (preserves build/ cache for faster rebuilds)"""
    print_step(1, 4, "Cleaning Previous Build Output")

    # Only clean dist/ - preserve build/ folder for PyInstaller cache
    dirs_to_clean = ["dist"]

    for dir_name in dirs_to_clean:
        directory = ROOT / dir_name
        if directory.exists():
            if directory.resolve().parent != ROOT.resolve() or directory.is_symlink() or directory.is_junction():
                raise RuntimeError("Build output path is outside the workspace")
            try:
                shutil.rmtree(directory)
                print(f"[OK] Removed {dir_name}/")
            except Exception as e:
                print(f"[ERROR] Failed to remove {dir_name}/: {e}")
                return False

    # Check if build cache exists
    if (ROOT / "build").exists():
        print("[INFO] Preserved build/ folder for faster incremental builds")
    else:
        print("[INFO] No build/ cache found - this will be a full build")

    # Note: injection/ directories are no longer cleaned as they contain real scripts
    # that need to be preserved (tools, config, etc.)

    return True


def build_pengu_loader():
    """Build the vendored Pengu Loader source before packaging OKDEV."""
    print_step(2, 4, "Building Pengu Loader From Source")

    script = ROOT / "scripts" / "build_pengu_loader.py"
    result = subprocess.run([sys.executable, str(script)], check=False, cwd=ROOT)
    if result.returncode != 0:
        print(f"[ERROR] Pengu Loader source build failed with exit code {result.returncode}")
        return False

    return True


def build_cslol_stub():
    """Build the stand-in cslol-dll.dll that mod-tools.exe needs to start."""
    script = ROOT / "scripts" / "build_cslol_stub.py"
    result = subprocess.run([sys.executable, str(script)], check=False, cwd=ROOT)
    if result.returncode != 0:
        print(f"[ERROR] cslol-dll stub build failed with exit code {result.returncode}")
        return False

    return True


def check_relay_config():
    """Default to no party relay until an OKDEV-owned service is configured."""
    config = ROOT / "party" / "network" / "relay_config.py"
    if not config.exists():
        config.write_text('RELAY_URL = ""\n', encoding="utf-8")
        print('[INFO] Party relay is not configured; solo use remains available.')
    elif "RELAY_URL" not in config.read_text(encoding="utf-8"):
        print('[ERROR] relay_config.py must define RELAY_URL')
        return False

    return True


def build_with_pyinstaller():
    """Build executable using PyInstaller with multi-threading"""
    print_step(3, 4, "Building with PyInstaller (Multi-threaded)")

    # Use spec file which has all the configuration
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "OKDEV.spec",
    ]

    print(f"Running: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True, cwd=ROOT)
        print("\n[OK] PyInstaller build completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Build failed: {e}")
        return False


def organize_output():
    """Organize output files and verify"""
    print_step(4, 4, "Organizing Output & Verification")

    dist_folder = ROOT / "dist/OKDEV"

    if not dist_folder.exists():
        print("[ERROR] Build output not found!")
        return False

    shutil.copy2(ROOT / "assets/icon.ico", dist_folder / "icon.ico")
    return True


def main():
    """Main build process"""
    print_header("OKDEV - PyInstaller Build")

    start_time = time.time()

    # Execute build steps
    if not check_relay_config():
        sys.exit(1)

    if not clean_previous_builds():
        sys.exit(1)

    # --skip-pengu-loader packages the existing Pengu Loader build as-is
    if "--skip-pengu-loader" not in sys.argv[1:] and not build_pengu_loader():
        sys.exit(1)

    if "--skip-cslol-stub" in sys.argv[1:]:
        # Local repair builds can reuse the matching runtime from an installed OKDEV.
        for name in ("cslol-dll.dll", "cslol-dll.stub"):
            if not (ROOT / "injection" / "tools" / name).is_file():
                print(f"[ERROR] Existing {name} is required with --skip-cslol-stub")
                sys.exit(1)
    elif not build_cslol_stub():
        sys.exit(1)

    if subprocess.run([sys.executable, str(ROOT / "scripts/build_okdev_core.py")], cwd=ROOT).returncode:
        sys.exit(1)
    if not build_with_pyinstaller():
        sys.exit(1)

    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--windowed", "--name", "OKDEV-Updater", "--icon", str(ROOT / "assets/icon.ico"),
        "--distpath", str(ROOT / "dist/OKDEV"), "--workpath", str(ROOT / "build/updater"),
        "--specpath", str(ROOT / "build"), str(ROOT / "okdev_update_helper.py")], cwd=ROOT, check=True)
    if not organize_output():
        print("[WARNING] Verification incomplete, but build may have succeeded")

    # Print summary
    elapsed_time = time.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)

    print_header("[OK] BUILD COMPLETED SUCCESSFULLY!")

    exe_path = ROOT / "dist/OKDEV/OKDEV.exe"

    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"Executable: {exe_path}")
        print(f"Size: {size_mb:.1f} MB")
        print(f"Build time: {minutes}m {seconds}s")

        print(f"\nYour application is ready!")
        print(f"\nMode: STANDALONE (folder with all dependencies)")
        print(f"  - All DLLs and dependencies included")
        print(f"  - CSLOL tools included")

        print(f"\nProtection:")
        print(f"  - Python bytecode (not raw source)")
        print(f"  - Requires decompiler tools to reverse")
        print(f"  - Good enough against casual theft")

        print(f"\nTo test:")
        print(f"  cd dist\\OKDEV")
        print(f"  OKDEV.exe")
    else:
        print("[ERROR] Executable not found!")
        sys.exit(1)


if __name__ == "__main__":
    main()
