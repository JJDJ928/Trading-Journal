#!/usr/bin/env bash
# Build "Rinse Tracker.app" and dist/Rinse-Tracker.dmg. Run on a Mac (or the GitHub Actions macOS runner).
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
$PY scripts/make_icon.py build/icon.icns

$PY -m PyInstaller --noconfirm --windowed \
  --name "Rinse Tracker" \
  --icon build/icon.icns \
  --osx-bundle-identifier com.rinsetracker.app \
  --add-data "rinse_tracker/static:rinse_tracker/static" \
  desktop.py

# Check the packaged app actually starts and serves its pages.
"dist/Rinse Tracker.app/Contents/MacOS/Rinse Tracker" --self-test

# Disk image with a drag-to-Applications shortcut.
mkdir -p build/dmg
cp -R "dist/Rinse Tracker.app" build/dmg/
ln -s /Applications build/dmg/Applications
hdiutil create -volname "Rinse Tracker" -srcfolder build/dmg -ov -format UDZO dist/Rinse-Tracker.dmg

echo "Built dist/Rinse-Tracker.dmg"
