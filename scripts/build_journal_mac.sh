#!/usr/bin/env bash
# Build "Trading Journal.app" and dist/Trading-Journal.dmg. Run on a Mac (or the GitHub Actions macOS runner).
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PYTHON:-python3}
if [ -z "${CI:-}" ]; then
  # Local builds use their own virtualenv so nothing is installed system-wide.
  $PY -m venv .venv-build
  # shellcheck disable=SC1091
  . .venv-build/bin/activate
  PY=python
fi

$PY -m pip install --upgrade pip
$PY -m pip install -r requirements.txt -r requirements-desktop.txt

rm -rf build dist
mkdir -p build
$PY scripts/make_journal_icon.py build/icon.icns

$PY -m PyInstaller --noconfirm --windowed \
  --name "Trading Journal" \
  --icon build/icon.icns \
  --osx-bundle-identifier com.tradingjournal.app \
  --add-data "journal/static:journal/static" \
  journal_desktop.py

# Check the packaged app actually starts and serves its pages.
"dist/Trading Journal.app/Contents/MacOS/Trading Journal" --self-test

# Disk image with a drag-to-Applications shortcut.
mkdir -p build/dmg
cp -R "dist/Trading Journal.app" build/dmg/
ln -s /Applications build/dmg/Applications
hdiutil create -volname "Trading Journal" -srcfolder build/dmg -ov -format UDZO dist/Trading-Journal.dmg

echo "Built dist/Trading-Journal.dmg"
