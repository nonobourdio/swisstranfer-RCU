#!/usr/bin/env python3
"""
Build script for SwissTransfer RCU — produces two standalone .exe files:

  1. dist/SwissTransferRCU.exe — the main upload tool (console app)
  2. dist/setup.exe            — the GUI installer/uninstaller

Usage:
  python build.py          # Build both exes
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
MAIN_EXE_NAME = "SwissTransferRCU"

INSTALLER_SCRIPT = ROOT / "installer_gui.py"
INSTALLER_EXE_NAME = "setup"


def clean():
    """Remove previous build artifacts."""
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            print(f"Removing {d}")
            shutil.rmtree(d)
    for spec in ROOT.glob("*.spec"):
        spec.unlink()


def _run_pyinstaller(args, label):
    """Run PyInstaller with given args."""
    print(f"\n{'='*60}")
    print(f"Building: {label}")
    print(f"{'='*60}\n")

    result = subprocess.run(args, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\n❌ BUILD FAILED: {label}")
        sys.exit(1)


def build_main():
    """Build the main SwissTransferRCU.exe."""
    icon_arg = str(ICON) if ICON.exists() else "NONE"
    _run_pyinstaller([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", MAIN_EXE_NAME,
        "--console",                    # Console for progress output
        "--noconfirm",
        "--clean",
        "--add-data", f"icons{os.pathsep}icons",
        "--icon", icon_arg,
        "--hidden-import", "playwright",
        "--hidden-import", "playwright.sync_api",
        "--hidden-import", "playwright._impl",
        "--collect-all", "playwright",
        str(MAIN_SCRIPT),
    ], "Main exe (SwissTransferRCU.exe)")

    exe = DIST_DIR / f"{MAIN_EXE_NAME}.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"  ✅ {exe}  ({size_mb:.1f} MB)")
    else:
        print(f"  ❌ {exe} not found!")
        sys.exit(1)


def build_installer():
    """Build setup.exe (GUI installer)."""
    icon_arg = str(ICON) if ICON.exists() else "NONE"
    _run_pyinstaller([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", INSTALLER_EXE_NAME,
        "--windowed",                    # GUI app — no console window
        "--noconfirm",
        "--clean",
        "--add-data", f"icons{os.pathsep}icons",
        "--icon", icon_arg,
        str(INSTALLER_SCRIPT),
    ], "Installer (setup.exe)")

    exe = DIST_DIR / f"{INSTALLER_EXE_NAME}.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"  ✅ {exe}  ({size_mb:.1f} MB)")
    else:
        print(f"  ❌ {exe} not found!")
        sys.exit(1)


def main():
    if "--clean" in sys.argv:
        clean()

    print(f"Output directory: {DIST_DIR}")
    build_main()
    build_installer()

    # Summary
    print(f"\n{'='*60}")
    print("BUILD COMPLETE!")
    print(f"{'='*60}")
    main_exe = DIST_DIR / f"{MAIN_EXE_NAME}.exe"
    setup_exe = DIST_DIR / f"{INSTALLER_EXE_NAME}.exe"
    total = main_exe.stat().st_size + setup_exe.stat().st_size
    print(f"  {main_exe.name:.<30s} {main_exe.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  {setup_exe.name:.<30s} {setup_exe.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  {'Total':.<30s} {total / 1024 / 1024:.1f} MB")
    print(f"\nDistribute BOTH files together. Run setup.exe to install.")


if __name__ == "__main__":
    main()
