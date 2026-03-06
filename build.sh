#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# build.sh — Build PassLock standalone executables for the current OS.
#
# Prerequisites:
#   pip install pyinstaller
#
# Usage:
#   chmod +x build.sh
#   ./build.sh
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== PassLock Build Script ==="
echo "OS: $(uname -s) $(uname -m)"
echo ""

# Ensure pyinstaller is installed
if ! command -v pyinstaller &>/dev/null; then
    echo "Installing PyInstaller…"
    pip install pyinstaller
fi

echo "Building standalone executable…"
pyinstaller passlock.spec --clean --noconfirm

OS="$(uname -s)"
case "$OS" in
    Darwin)
        echo ""
        echo "✅ macOS build complete!"
        echo "   App bundle: dist/PassLock.app"
        echo "   Executable: dist/PassLock"
        echo ""
        echo "Creating DMG installer…"
        DMG_NAME="PassLock-1.0.0-macOS.dmg"
        rm -rf dist/dmg_staging
        mkdir -p dist/dmg_staging
        cp -R dist/PassLock.app dist/dmg_staging/
        ln -sf /Applications dist/dmg_staging/Applications
        rm -f "dist/$DMG_NAME"
        hdiutil create -volname "PassLock" -srcfolder dist/dmg_staging \
            -ov -format UDZO "dist/$DMG_NAME"
        rm -rf dist/dmg_staging
        echo ""
        echo "✅ DMG installer ready: dist/$DMG_NAME"
        echo "   Share this single file — users drag PassLock.app to Applications."
        ;;
    Linux)
        echo ""
        echo "✅ Linux build complete!"
        echo "   Executable: dist/passlock"
        echo ""
        echo "To install system-wide:"
        echo "   sudo cp dist/passlock /usr/local/bin/"
        ;;
    *)
        echo ""
        echo "✅ Build complete!"
        echo "   Executable: dist/"
        ;;
esac
