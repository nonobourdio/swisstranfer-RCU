#!/usr/bin/env python3
"""
Build script for SwissTransfer RCU — produces a single standalone .exe.

  dist/SwissTransferRCU.exe — main upload tool + installer GUI

Usage:
  python build.py          # Build the exe
  python build.py --clean  # Clean build artifacts first
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
ICON = ROOT / "icons" / "swisstransfer.ico"

BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"

MAIN_SCRIPT = ROOT / "swisstransfer_upload.py"
EXE_NAME = "SwissTransferRCU"


def clean():
    """Remove previous build artifacts."""
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            print(f"Removing {d}")
            shutil.rmtree(d)
    for spec in ROOT.glob("*.spec"):
        spec.unlink()


def build():
    """Run PyInstaller to create the standalone exe."""
    if not MAIN_SCRIPT.exists():
        print(f"ERROR: {MAIN_SCRIPT} not found")
        sys.exit(1)

    icon_arg = str(ICON) if ICON.exists() else "NONE"

    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", EXE_NAME,
        "--console",                    # Console for upload progress; GUI launched on no-args
        "--noconfirm",
        "--clean",
        "--add-data", f"icons{os.pathsep}icons",
        "--icon", icon_arg,
        "--hidden-import", "playwright",
        "--hidden-import", "playwright.sync_api",
        "--hidden-import", "playwright._impl",
        "--collect-all", "playwright",
        str(MAIN_SCRIPT),
    ]

    print(f"Running PyInstaller...")
    print(f"  Output: {DIST_DIR / (EXE_NAME + '.exe')}")
    print()

    result = subprocess.run(args, cwd=str(ROOT))

    if result.returncode != 0:
        print(f"\nBUILD FAILED")
        sys.exit(1)

    exe_path = DIST_DIR / f"{EXE_NAME}.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\nBuild successful!")
        print(f"  {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print(f"\nBuild reported success but exe not found!")
        sys.exit(1)


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    build()
