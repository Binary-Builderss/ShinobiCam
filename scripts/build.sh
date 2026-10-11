#!/usr/bin/env bash
# Test + build PyInstaller (.app) + selftest + zip distribuibile, su macOS.
# Uso: ./scripts/build.sh [--skip-tests]
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
[ -x "$PY" ] || { echo "Ambiente assente: esegui prima scripts/setup.sh" >&2; exit 1; }
[ -f models/hand_landmarker.task ] || { echo "Modello mancante: esegui prima scripts/setup.sh" >&2; exit 1; }

if [ "${1:-}" != "--skip-tests" ]; then
    echo "== Test"
    "$PY" -m pytest -q
fi

echo "== PyInstaller"
"$PY" -m PyInstaller --noconfirm --clean ShinobiCam.spec
APP=dist/ShinobiCam.app

echo "== Selftest dell'app"
HOME_DIR="$(mktemp -d)"
SHINOBICAM_HOME="$HOME_DIR" "$APP/Contents/MacOS/ShinobiCam" --selftest || { cat "$HOME_DIR/selftest.txt"; exit 1; }
cat "$HOME_DIR/selftest.txt"

echo "== Pacchetto"
ditto -c -k --keepParent "$APP" dist/ShinobiCam-macos-arm64.zip
echo "Fatto: $APP  e  dist/ShinobiCam-macos-arm64.zip"
