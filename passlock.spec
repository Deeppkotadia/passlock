# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for PassLock.
Generates a single-file executable for the current OS.

Usage:
    pip install pyinstaller
    pyinstaller passlock.spec
"""

import platform
import sys

block_cipher = None

system = platform.system()

# ── Platform-specific settings ────────────────────────────────────────

if system == "Darwin":
    icon_file = None  # set to 'assets/icon.icns' if you have one
    exe_name = "PassLock"
    console = False
    bundle_info = {
        "CFBundleName": "PassLock",
        "CFBundleDisplayName": "PassLock",
        "CFBundleIdentifier": "com.passlock.app",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
    }
elif system == "Windows":
    icon_file = None  # set to 'assets/icon.ico' if you have one
    exe_name = "PassLock"
    console = False
    bundle_info = {}
else:  # Linux
    icon_file = None  # set to 'assets/icon.png' if you have one
    exe_name = "passlock"
    console = False
    bundle_info = {}


a = Analysis(
    ["passlock/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "passlock",
        "passlock.core",
        "passlock.cli",
        "passlock.gui",
        "passlock.logger",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=console,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

# macOS .app bundle
if system == "Darwin":
    app = BUNDLE(
        exe,
        name="PassLock.app",
        icon=icon_file,
        bundle_identifier="com.passlock.app",
        info_plist=bundle_info,
    )
