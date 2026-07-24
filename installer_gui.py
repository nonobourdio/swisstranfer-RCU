#!/usr/bin/env python3
"""
SwissTransfer RCU Installer — GUI installer that copies the main exe and
registers the context menu. This gets compiled to setup.exe by PyInstaller.

When run, it shows a simple installer window with Install/Uninstall buttons.
"""

import os
import sys
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

APP_NAME = "SwissTransfer RCU"
APP_VERSION = "1.0.0"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "SwissTransferRCU"

# If running as setup.exe, the main exe should be next to it
if getattr(sys, "frozen", False):
    _SETUP_DIR = Path(sys.executable).parent
else:
    _SETUP_DIR = Path(__file__).parent.resolve()

MAIN_EXE_NAME = "SwissTransferRCU.exe"
MAIN_EXE_SOURCE = _SETUP_DIR / MAIN_EXE_NAME
ICON_SOURCE = _SETUP_DIR / "icons" / "swisstransfer.ico"


def is_installed():
    """Check if the tool is already installed."""
    return (INSTALL_DIR / MAIN_EXE_NAME).exists()


def install():
    """Copy files to install dir and run --setup."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    (INSTALL_DIR / "icons").mkdir(exist_ok=True)

    # Copy main exe
    if not MAIN_EXE_SOURCE.exists():
        return False, f"Cannot find {MAIN_EXE_NAME} next to setup.exe.\n" \
                      f"Expected: {MAIN_EXE_SOURCE}"
    shutil.copy2(MAIN_EXE_SOURCE, INSTALL_DIR / MAIN_EXE_NAME)

    # Copy icons
    if ICON_SOURCE.exists():
        shutil.copy2(ICON_SOURCE, INSTALL_DIR / "icons" / "swisstransfer.ico")

    # Run --setup via the installed exe
    exe = str(INSTALL_DIR / MAIN_EXE_NAME)
    result = subprocess.run([exe, "--setup"], capture_output=True, text=True)

    if result.returncode != 0:
        return False, f"Setup failed:\n{result.stderr}"

    return True, result.stdout


def uninstall():
    """Run --uninstall then delete files."""
    exe = INSTALL_DIR / MAIN_EXE_NAME
    if exe.exists():
        subprocess.run([str(exe), "--uninstall"], capture_output=True)

    # Force-clean directory
    if INSTALL_DIR.exists():
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)

    return True, "Uninstalled successfully."


class InstallerGUI:
    def __init__(self, root):
        self.root = root
        root.title(f"{APP_NAME} Installer")
        root.geometry("440x320")
        root.resizable(False, False)

        # Try to set icon
        if ICON_SOURCE.exists():
            try:
                root.iconbitmap(default=str(ICON_SOURCE))
            except Exception:
                pass

        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Info.TLabel", font=("Segoe UI", 10))
        style.configure("Status.TLabel", font=("Segoe UI", 9), foreground="gray")

        # Title
        ttk.Label(root, text="SwissTransfer RCU", style="Title.TLabel").pack(pady=(30, 5))
        ttk.Label(root, text=f"v{APP_VERSION} — Right-click upload for Windows Explorer",
                  style="Info.TLabel").pack(pady=(0, 20))

        # Status
        self.status_var = tk.StringVar()
        installed = is_installed()
        self.status_var.set(
            "[Installed]" if installed else "[Not installed]"
        )
        self.status_label = ttk.Label(root, textvariable=self.status_var,
                                       style="Status.TLabel")
        self.status_label.pack(pady=10)

        # Buttons
        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=20)

        self.install_btn = ttk.Button(btn_frame, text="Install", command=self.do_install,
                                       width=15)
        self.install_btn.pack(side=tk.LEFT, padx=10)

        self.uninstall_btn = ttk.Button(btn_frame, text="Uninstall", command=self.do_uninstall,
                                         width=15)
        self.uninstall_btn.pack(side=tk.LEFT, padx=10)

        # Progress label
        self.progress_var = tk.StringVar()
        ttk.Label(root, textvariable=self.progress_var, style="Status.TLabel").pack(pady=10)

        if installed:
            self.install_btn.config(state=tk.DISABLED)
        else:
            self.uninstall_btn.config(state=tk.DISABLED)

    def do_install(self):
        self.progress_var.set("Installing...")
        self.root.update()

        success, msg = install()
        if success:
            self.status_var.set("[Installed]")
            self.install_btn.config(state=tk.DISABLED)
            self.uninstall_btn.config(state=tk.NORMAL)
            self.progress_var.set("")
            messagebox.showinfo(APP_NAME,
                "Installation complete!\n\n"
                "Right-click any file in Explorer → 'Show more options' → "
                "'Envoyer via SwissTransfer'\n\n"
                "You may need to restart Explorer for the menu to appear.")
        else:
            self.progress_var.set("Installation failed!")
            messagebox.showerror(APP_NAME, msg)

    def do_uninstall(self):
        confirm = messagebox.askyesno(APP_NAME, "Remove SwissTransfer RCU?")
        if not confirm:
            return

        self.progress_var.set("Uninstalling...")
        self.root.update()

        success, msg = uninstall()
        if success:
            self.status_var.set("[Not installed]")
            self.install_btn.config(state=tk.NORMAL)
            self.uninstall_btn.config(state=tk.DISABLED)
            self.progress_var.set("")
            messagebox.showinfo(APP_NAME, "SwissTransfer RCU has been removed.")
        else:
            self.progress_var.set("Uninstall failed!")
            messagebox.showerror(APP_NAME, msg)


if __name__ == "__main__":
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()
