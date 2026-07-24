# SwissTransfer RCU

**Right-click → Upload via SwissTransfer** for Windows Explorer.

Upload files to [SwissTransfer](https://www.swisstransfer.com) (Infomaniak) directly from the Windows context menu. No GUI, no browser tab — just right-click, upload, and the download link is copied to your clipboard.

## Features

- **Right-click integration** — "Envoyer via SwissTransfer" on files and folders
- **Auto-credential detection** — finds your SwissTransfer email/token from any installed browser (Firefox, Chrome, Edge, Brave)
- **Multi-file upload** — select multiple files or a whole folder
- **Large file support** — chunked uploads up to 50 GB
- **Link copied to clipboard** — ready to paste anywhere
- **reCAPTCHA bypass** — headless Chromium token generation (~3s)
- **Zero dependencies on target machine** — standalone .exe, uses the browser already installed

## How It Works

1. **Credential detection**: Scans browser localStorage (SQLite for Firefox, LevelDB for Chromium-based) across all installed browsers to find your SwissTransfer `authorEmail` and `authorEmailToken`.
2. **reCAPTCHA**: Launches a headless instance of your installed Chromium browser (Brave/Chrome/Edge) to solve reCAPTCHA v3 transparently.
3. **Upload**: Creates a container via the SwissTransfer API, uploads in 50 MB chunks, finalizes, and retrieves the `linkUUID`.
4. **Clipboard**: Copies `https://www.swisstransfer.com/d/{linkUUID}` to your clipboard.

## Build

### Prerequisites

- Python 3.12+ with `playwright` and `requests`
- PyInstaller (`pip install pyinstaller`)
- Icons in `icons/` directory

### Build both exes

```bash
python build.py --clean
```

Produces in `dist/`:
| File | Size | Purpose |
|---|---|---|
| `SwissTransferRCU.exe` | ~53 MB | Main upload tool (console) |
| `setup.exe` | ~11 MB | GUI installer/uninstaller |

### Distribute

Ship **both** files together in the same folder. Users run `setup.exe` to install.

## Install

1. Run `setup.exe`
2. Click **Install**
3. Right-click any file in Explorer → "Show more options" → "Envoyer via SwissTransfer"

> **Note**: On Windows 11, the context menu entry appears under "Show more options" (or with Shift+Right-click).

## Uninstall

Run `setup.exe` → **Uninstall**, or:
```bash
SwissTransferRCU.exe --uninstall
```

## Usage (CLI)

```bash
# Upload files
SwissTransferRCU.exe file1.pdf file2.zip

# Upload with 30-day link validity
SwissTransferRCU.exe --duration 30 bigfile.iso

# Install/uninstall context menu manually
SwissTransferRCU.exe --setup
SwissTransferRCU.exe --uninstall
```

## Requirements

- Windows 10/11
- A Chromium-based browser installed (Brave, Chrome, or Edge) — used for headless reCAPTCHA
- SwissTransfer email entered at least once on swisstransfer.com in any browser

## API Details

Reverse-engineered from the SwissTransfer frontend (`main-*.js`):

- **Base**: `https://www.swisstransfer.com/api`
- **Endpoints**: `POST /containers` → `POST /uploadChunk/{containerUUID}/{fileUUID}/{index}/{isLastChunk}` → `POST /uploadComplete`
- **Chunk size**: 50 MB (`52,428,800` bytes)
- **reCAPTCHA v3 site key**: `6LdcMKgUAAAAAE-v9oXOW9sNCWRiuZga1ayC7a6L`
- **Download link**: `https://www.swisstransfer.com/d/{linkUUID}` (NOT `containerUUID`)

## License

Personal use. SwissTransfer is a trademark of Infomaniak.
