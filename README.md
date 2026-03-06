# PassLock — Cross-Platform File & Folder Password Protection

Encrypt and decrypt files and folders on **Windows**, **macOS**, and **Linux** using AES-256 encryption — with both a **GUI** and a **CLI**.

## Features

- **AES-256-CBC** encryption with PBKDF2-HMAC-SHA256 key derivation (600,000 iterations)
- **HMAC-SHA256** integrity verification (detects tampering and wrong passwords)
- Encrypt individual **files** or entire **folders**
- **Graphical UI** (tkinter) — no command line needed
- **CLI** for scripting and terminal workflows
- Cross-platform — works on Windows, macOS, and Linux (Python 3.9+)
- Installable as a Python package or standalone executable

---

## Quick Start

### Option A — Install as a Python package

```bash
# From the project directory:
pip install .

# Launch the GUI:
passlock-gui          # or: python -m passlock

# Use the CLI:
passlock lock secret.pdf
passlock unlock secret.pdf.locked
```

### Option B — Run without installing

```bash
pip install -r requirements.txt

# GUI
python -m passlock

# CLI
python -m passlock lock /path/to/file
python -m passlock unlock /path/to/file.locked
```

### Option C — Standalone executable (no Python needed)

See [Building Standalone Executables](#building-standalone-executables) below.

---

## GUI

Launch the graphical interface:

```bash
passlock-gui          # if installed via pip
python -m passlock    # without installing
passlock gui          # CLI sub-command
```

The GUI lets you:
- Browse for files or folders
- Enter your password in a dialog (with confirmation for locking)
- Toggle "keep original" option
- See a real-time log of operations

---

## CLI Usage

### Lock (encrypt) a file

```bash
passlock lock /path/to/secret.pdf
```

You'll be prompted to enter and confirm a password. The original file is replaced with `secret.pdf.locked`.

### Lock (encrypt) a folder

```bash
passlock lock /path/to/my_folder
```

The folder is archived, encrypted, and saved as `my_folder.locked`. The original folder is removed.

### Unlock (decrypt)

```bash
passlock unlock /path/to/secret.pdf.locked
passlock unlock /path/to/my_folder.locked
```

### Keep originals

Use `--keep` to retain the original file/folder after locking or the `.locked` file after unlocking:

```bash
passlock lock   myfile.txt --keep
passlock unlock myfile.txt.locked --keep
```

---

## Building Standalone Executables

Build a single-file executable for your OS using PyInstaller:

### macOS / Linux

```bash
chmod +x build.sh
./build.sh
```

**macOS output:** `dist/PassLock.app` (drag to Applications)
**Linux output:** `dist/passlock` (copy to `/usr/local/bin/`)

### Windows

```cmd
build.bat
```

**Output:** `dist\PassLock.exe`

To create a proper Windows installer, compile `installer_win.iss` with [Inno Setup](https://jrsoftware.org/isinfo.php).

---

## OS Compatibility

| OS        | Python  | GUI   | CLI   | Standalone |
|-----------|---------|-------|-------|------------|
| Windows 10/11  | 3.9 – 3.13 | ✅ | ✅ | .exe (PyInstaller) |
| macOS 12+      | 3.9 – 3.13 | ✅ | ✅ | .app bundle (PyInstaller) |
| Ubuntu 20.04+  | 3.9 – 3.13 | ✅ | ✅ | binary (PyInstaller) |
| Debian / Fedora / Arch | 3.9+ | ✅ | ✅ | binary (PyInstaller) |

> **Note (Linux):** tkinter may need to be installed separately:
> `sudo apt install python3-tk` (Debian/Ubuntu) or `sudo dnf install python3-tkinter` (Fedora).

---

## Security Details

| Property | Value |
|---|---|
| Cipher | AES-256-CBC |
| Key derivation | PBKDF2-HMAC-SHA256, 600 000 iterations |
| Salt | 32 bytes, cryptographically random |
| IV | 16 bytes, cryptographically random |
| Integrity | HMAC-SHA256 (encrypt-then-MAC) |
| Padding | PKCS7 |

## Encrypted File Format

```
PLCK (4 B) | version (1 B) | salt (32 B) | IV (16 B) | ciphertext (var) | HMAC (32 B)
```

## Project Structure

```
passlock/
├── __init__.py      # package metadata & version
├── __main__.py      # python -m passlock entry point
├── core.py          # encryption engine
├── cli.py           # command-line interface
└── gui.py           # graphical interface (tkinter)
pyproject.toml       # package config (pip install .)
passlock.spec        # PyInstaller build spec
build.sh             # macOS / Linux build script
build.bat            # Windows build script
installer_win.iss    # Inno Setup script (Windows installer)
requirements.txt     # pip dependencies
```

## Requirements

- Python 3.9+
- `cryptography` package
- `tkinter` (included with Python on Windows/macOS; install separately on some Linux distros)
