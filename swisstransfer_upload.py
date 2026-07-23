#!/usr/bin/env python3
"""
SwissTransfer Upload Tool — Right-click "Send via SwissTransfer" for Windows Explorer.

Uploads files to SwissTransfer via the Infomaniak API and copies the download
link to the clipboard. Multi-file, multi-chunk, with progress display.

Usage:
  python swisstransfer_upload.py <file1> [file2] [file3] ...
  python swisstransfer_upload.py --setup       # Install right-click context menu
  python swisstransfer_upload.py --uninstall    # Remove right-click context menu

Requirements:
  - Python 3.12+ with: playwright, requests  (see requirements.txt)
  - A Chromium-based browser installed (Brave/Chrome/Edge)
  - SwissTransfer email already entered at least once on swisstransfer.com
    in any browser (the script auto-detects it from browser localStorage)
"""

import json
import os
import re
import sys
import glob
import time
import shutil
import sqlite3
import tempfile
import argparse
import subprocess
from pathlib import Path

try:
    import winreg
except ImportError:
    winreg = None

# ─── Configuration ───────────────────────────────────────────────────────────

# Python interpreter to use (auto-detect current interpreter by default)
PYTHON_EXE = sys.executable

# Browser executable for headless reCAPTCHA — auto-detect at runtime (see below)
BROWSER_EXE = None

# SwissTransfer API constants (reverse-engineered from the SwissTransfer frontend)
API_BASE = "https://www.swisstransfer.com/api"
CAPTCHA_SITE_KEY_V3 = "6LdcMKgUAAAAAE-v9oXOW9sNCWRiuZga1ayC7a6L"
CHUNK_SIZE = 52428800  # 50 MB — from SwissTransfer frontend config
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
API_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": USER_AGENT,
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://www.swisstransfer.com",
    "Referer": "https://www.swisstransfer.com/en",
}

# Script directory (for icon path)
SCRIPT_DIR = Path(__file__).parent.resolve()
ICON_PATH = SCRIPT_DIR / "icons" / "swisstransfer.ico"

# ─── Browser auto-detection ──────────────────────────────────────────────────

_CHROMIUM_BROWSER_PATHS = [
    # (name, path)
    ("brave",  r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ("brave",  r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ("chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    ("chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ("edge",   r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ("edge",   r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]


def _detect_chromium_browser():
    """Find a Chromium-based browser executable for headless reCAPTCHA."""
    if BROWSER_EXE:
        return BROWSER_EXE
    for name, path in _CHROMIUM_BROWSER_PATHS:
        if os.path.isfile(path):
            return path
    return None


# ─── Credential auto-detection (any browser) ─────────────────────────────────

def _get_default_browser():
    """Detect default browser from Windows registry."""
    if not winreg:
        return "unknown"
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
        )
        prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        winreg.CloseKey(key)
        p = prog_id.lower()
        if "firefox" in p:
            return "firefox"
        if "chrome" in p:
            return "chrome"
        if "brave" in p:
            return "brave"
        if "edge" in p:
            return "edge"
        return p
    except Exception:
        return "unknown"


_FIREFOX_PROFILES = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles")
_CHROMIUM_DATA_DIRS = {
    "edge":   os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
    "brave":  os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
    "chrome": os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
}

_KNOWN_LS_KEYS = {
    "ST_authorEmail", "ST_recipientsEmails", "_grecaptcha",
    "backgrounds", "backgrounds_date", "language",
    "ksuite-bridge-swisstransfer-client", "ksuite-bridge-wc-client",
    "ST_isMailModeCookie", "ST_CGU_approbation", "ST_COUNTRY",
}


def _read_firefox_credentials():
    """Scan all Firefox profiles for SwissTransfer localStorage (SQLite format)."""
    if not os.path.isdir(_FIREFOX_PROFILES):
        return None, None
    for profile in os.listdir(_FIREFOX_PROFILES):
        db = os.path.join(
            _FIREFOX_PROFILES, profile, "storage", "default",
            "https+++www.swisstransfer.com", "ls", "data.sqlite",
        )
        if not os.path.exists(db):
            continue
        tmp = os.path.join(tempfile.gettempdir(), f"ff_st_{profile}.sqlite")
        try:
            shutil.copy2(db, tmp)
        except OSError:
            continue
        email, token = None, None
        try:
            conn = sqlite3.connect(tmp)
            c = conn.cursor()
            c.execute("SELECT value FROM data WHERE key = 'ST_authorEmail'")
            row = c.fetchone()
            if row:
                val = row[0]
                email = val.decode("utf-8") if isinstance(val, bytes) else val
            if email:
                c.execute("SELECT key, value FROM data")
                for k, v in c.fetchall():
                    if k not in _KNOWN_LS_KEYS and len(k) > 40:
                        token = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                        break
            conn.close()
        except sqlite3.Error:
            pass
        if email:
            log(f"  Credentials from Firefox ({profile})")
            return email, token
    return None, None


def _read_chromium_credentials(browser_name, data_dir):
    """Scan Chromium LevelDB for SwissTransfer localStorage (raw binary parse)."""
    if not os.path.isdir(data_dir):
        return None, None
    st_origin = b"https://www.swisstransfer.com"
    for profile in os.listdir(data_dir):
        leveldb = os.path.join(data_dir, profile, "Local Storage", "leveldb")
        if not os.path.isdir(leveldb):
            continue
        blob = b""
        for fp in sorted(glob.glob(os.path.join(leveldb, "*"))):
            try:
                with open(fp, "rb") as f:
                    blob += f.read()
            except OSError:
                continue
        if st_origin not in blob:
            continue
        email_key = b"_https://www.swisstransfer.com\x00\x01ST_authorEmail"
        idx = blob.find(email_key)
        email = _extract_leveldb_value(blob, idx + len(email_key)) if idx >= 0 else None
        token = _scan_chromium_token(blob) if email else None
        if email:
            log(f"  Credentials from {browser_name.capitalize()} ({profile})")
            return email, token
    return None, None


def _extract_leveldb_value(data, offset):
    """Extract a UTF-8 string from Chromium LevelDB binary at the given offset."""
    if offset >= len(data):
        return None
    for skip in range(5):
        pos = offset + skip
        if pos + 2 > len(data):
            break
        if data[pos] in (0x00, 0x01, 0x02):  # localStorage type marker
            pos += 1
            length, shift = 0, 0
            while pos < len(data):
                byte = data[pos]
                pos += 1
                length |= (byte & 0x7F) << shift
                if byte < 0x80:
                    break
                shift += 7
            if 0 < length <= len(data) - pos:
                raw = data[pos : pos + length]
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        return raw.decode("latin-1")
                    except UnicodeDecodeError:
                        pass
    # Fallback: printable ASCII run
    for skip in range(6):
        pos = offset + skip
        end = pos
        while end < len(data) and 32 <= data[end] < 127:
            end += 1
        text = data[pos:end].decode("ascii", errors="ignore")
        if "@" in text and len(text) > 5:
            return text
    return None


def _scan_chromium_token(data):
    """Find the authorEmailToken in LevelDB (hex-key → base64 value)."""
    pattern = re.compile(
        rb"_https://www\.swisstransfer\.com\x00\x01[0-9a-f]{60,200}"
    )
    for m in pattern.finditer(data):
        val = _extract_leveldb_value(data, m.end())
        if val and val.startswith("eyJ"):
            return val
    return None


def read_credentials():
    """Auto-detect SwissTransfer credentials from any installed browser."""
    default = _get_default_browser()
    log(f"Default browser: {default}")

    has_firefox = os.path.isdir(_FIREFOX_PROFILES)
    chromium = {n: p for n, p in _CHROMIUM_DATA_DIRS.items() if os.path.isdir(p)}

    # Build scan order: default browser first, then others
    scan = []
    if default == "firefox" and has_firefox:
        scan.append(("firefox", None))
    for n, p in chromium.items():
        scan.append((n, p))
    if has_firefox and ("firefox", None) not in scan:
        scan.append(("firefox", None))

    for name, path in scan:
        if name == "firefox":
            email, token = _read_firefox_credentials()
        else:
            email, token = _read_chromium_credentials(name, path)
        if email:
            return email, token
    return None, None


# ─── reCAPTCHA token via headless browser ────────────────────────────────────

def get_recaptcha_token():
    """Launch a headless Chromium browser to obtain a reCAPTCHA v3 token."""
    from playwright.sync_api import sync_playwright

    browser_exe = _detect_chromium_browser()
    if not browser_exe:
        raise RuntimeError(
            "No Chromium-based browser found. Install Brave, Chrome, or Edge."
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=browser_exe,
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            user_agent=USER_AGENT, viewport={"width": 1280, "height": 720}
        )
        page = ctx.new_page()
        page.goto(
            "https://www.swisstransfer.com/en",
            wait_until="networkidle",
            timeout=30000,
        )
        page.wait_for_timeout(1500)

        page.evaluate(
            f"""() => new Promise((res, rej) => {{
                const s = document.createElement('script');
                s.src = 'https://www.google.com/recaptcha/api.js?render={CAPTCHA_SITE_KEY_V3}';
                s.onload = res; s.onerror = () => rej('recaptcha load failed');
                document.head.appendChild(s);
            }})"""
        )
        page.wait_for_timeout(2000)

        token = page.evaluate(
            f"""() => new Promise((res, rej) => {{
                grecaptcha.execute('{CAPTCHA_SITE_KEY_V3}', {{action: 'upload'}})
                    .then(res).catch(e => rej(e.toString()));
            }})"""
        )
        browser.close()
        return token


# ─── Upload logic ────────────────────────────────────────────────────────────

def upload_files(file_paths, duration="1", author_email=None, author_email_token=None):
    """Upload files to SwissTransfer. Returns the download link URL."""
    import requests

    total_size = 0
    files_meta = []
    for fp in file_paths:
        size = os.path.getsize(fp)
        total_size += size
        files_meta.append({
            "name": os.path.basename(fp),
            "size": size,
            "type": "application/octet-stream",
        })

    log(f"Uploading {len(file_paths)} file(s), total: {_human_size(total_size)}")

    # 1. reCAPTCHA
    log("Obtaining reCAPTCHA token...")
    captcha = get_recaptcha_token()
    log(f"  Token: {len(captcha)} chars")

    # 2. Create container
    log("Creating SwissTransfer container...")
    resp = requests.post(
        f"{API_BASE}/containers",
        json={
            "duration": duration,
            "authorEmail": author_email or "",
            "authorEmailToken": author_email_token or "",
            "password": "",
            "message": "",
            "sizeOfUpload": total_size,
            "numberOfDownload": 1,
            "numberOfFile": len(file_paths),
            "recaptcha": captcha,
            "recaptchaVersion": 3,
            "lang": "fr_FR",
            "files": files_meta,
            "recipientsEmails": [],
        },
        headers=API_HEADERS,
    )
    data = resp.json()
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Container creation failed ({resp.status_code}): {json.dumps(data)}")

    container_uuid = data["container"]["UUID"]
    upload_host = data["uploadHost"]
    file_uuids = data["filesUUID"]
    log(f"  Container: {container_uuid}")
    log(f"  Upload host: {upload_host}")

    # 3. Upload chunks
    upload_headers = {
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://www.swisstransfer.com",
        "Referer": "https://www.swisstransfer.com/en",
        "Content-Type": "application/octet-stream",
    }

    for i, (fp, file_uuid) in enumerate(zip(file_paths, file_uuids)):
        fsize = os.path.getsize(fp)
        fname = os.path.basename(fp)
        n_chunks = max(1, (fsize + CHUNK_SIZE - 1) // CHUNK_SIZE)
        log(f"[{i+1}/{len(file_paths)}] {fname} ({_human_size(fsize)}, {n_chunks} chunk(s))")
        with open(fp, "rb") as f:
            for ci in range(n_chunks):
                chunk = f.read(CHUNK_SIZE)
                is_last = 1 if ci == n_chunks - 1 else 0
                url = f"https://{upload_host}/api/uploadChunk/{container_uuid}/{file_uuid}/{ci}/{is_last}"
                r = requests.post(url, data=chunk, headers=upload_headers)
                if r.status_code not in (200, 201):
                    raise RuntimeError(f"Chunk upload failed ({r.status_code}): {r.text}")
                if n_chunks > 1:
                    done = (ci + 1) * min(CHUNK_SIZE, fsize - ci * CHUNK_SIZE)
                    log(f"  Chunk {ci+1}/{n_chunks} — {done * 100 // fsize}%")

    # 4. Finalize
    log("Finalizing upload...")
    resp = requests.post(
        f"{API_BASE}/uploadComplete",
        json={"UUID": container_uuid, "lang": "fr_FR", "recipientsEmails": []},
        headers=API_HEADERS,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Upload completion failed ({resp.status_code}): {resp.text}")

    result = resp.json()
    link_uuid = result[0]["linkUUID"] if isinstance(result, list) else result.get("linkUUID")
    download_url = f"https://www.swisstransfer.com/d/{link_uuid}"
    log(f"Download link: {download_url}")
    return download_url


# ─── Utilities ───────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)


def _human_size(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def copy_to_clipboard(text):
    """Copy text to clipboard via PowerShell."""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
        capture_output=True,
    )


def notify(title, message):
    """Show a Windows message box (auto-dismiss after 4s)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxTimeoutW(0, message, title, 0x40, 0, 4000)
    except Exception:
        pass


# ─── Registry: install / uninstall context menu ──────────────────────────────

_REG_KEYS = [
    r"HKCU\Software\Classes\*\shell\SwissTransfer",
    r"HKCU\Software\Classes\Directory\shell\SwissTransfer",
    r"HKCU\Software\Classes\Directory\Background\shell\SwissTransfer",
]


def setup_registry():
    """Add 'Envoyer via SwissTransfer' to the Windows Explorer right-click menu."""
    script = str(SCRIPT_DIR / "swisstransfer_upload.py")
    python = PYTHON_EXE
    icon = str(ICON_PATH) if ICON_PATH.exists() else ""

    entries = [
        # (key, value_name, value_data)
        (_REG_KEYS[0], None, "Envoyer via SwissTransfer"),
        (_REG_KEYS[0], "Icon", icon),
        (_REG_KEYS[0] + r"\command", None, f'"{python}" "{script}" "%1"'),

        (_REG_KEYS[1], None, "Envoyer via SwissTransfer"),
        (_REG_KEYS[1], "Icon", icon),
        (_REG_KEYS[1] + r"\command", None, f'"{python}" "{script}" "%1"'),

        (_REG_KEYS[2], None, "Envoyer via SwissTransfer"),
        (_REG_KEYS[2], "Icon", icon),
        (_REG_KEYS[2] + r"\command", None, f'"{python}" "{script}" "%V"'),
    ]

    for key, name, val in entries:
        if name is None:
            cmd = ["reg", "add", key, "/ve", "/d", val, "/f"]
        else:
            cmd = ["reg", "add", key, "/v", name, "/t", "REG_SZ", "/d", val, "/f"]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            log(f"  Failed: {key}")
            return False

    log("Context menu installed! 'Envoyer via SwissTransfer' is now available.")
    log("You may need to restart Explorer (or log off/on) for changes to appear.")
    return True


def uninstall_registry():
    """Remove all SwissTransfer context menu entries."""
    for key in _REG_KEYS:
        subprocess.run(["reg", "delete", key, "/f"], capture_output=True)
    log("Context menu removed.")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SwissTransfer Upload Tool")
    parser.add_argument("files", nargs="*", help="Files to upload")
    parser.add_argument("--duration", default="1", choices=["1", "7", "15", "30"],
                        help="Link validity in days (default: 1)")
    parser.add_argument("--setup", action="store_true",
                        help="Install the right-click context menu")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove the right-click context menu")
    args = parser.parse_args()

    if args.setup:
        setup_registry()
        return
    if args.uninstall:
        uninstall_registry()
        return
    if not args.files:
        parser.error("No files specified. Use --setup to install the context menu.")

    # Expand directories
    all_files = []
    for path in args.files:
        if os.path.isdir(path):
            for item in os.listdir(path):
                full = os.path.join(path, item)
                if os.path.isfile(full):
                    all_files.append(full)
        elif os.path.isfile(path):
            all_files.append(path)

    if not all_files:
        log("No files found to upload.")
        return

    # Detect credentials
    log("Detecting credentials...")
    email, token = read_credentials()
    if not email:
        log("No SwissTransfer email found in any browser.")
        log("Visit swisstransfer.com and enter your email at least once.")
        return
    log(f"  Email: {email}")

    # Upload
    try:
        t0 = time.time()
        link = upload_files(
            all_files, duration=args.duration,
            author_email=email, author_email_token=token,
        )
        elapsed = time.time() - t0
        copy_to_clipboard(link)
        log(f"Link copied to clipboard!")
        log(f"Total time: {elapsed:.1f}s")
        notify("SwissTransfer", f"Upload complete! Link copied to clipboard.\n{link}")
    except Exception as e:
        log(f"Upload failed: {e}")
        notify("SwissTransfer", f"Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
