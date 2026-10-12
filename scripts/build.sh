#!/usr/bin/env bash
# Test + build PyInstaller (.app) + selftest + zip distribuibile, su macOS.
# Uso: ./scripts/build.sh [--skip-tests]
#
# Firma e notarizzazione (facoltative, vedi README §7):
#   SHINOBICAM_SIGN_ID="Developer ID Application: Nome (TEAMID)"  firma con hardened runtime
#   SHINOBICAM_NOTARY_PROFILE=shinobicam                          notarizza e "graffa" il ticket
# Senza variabili: firma ad-hoc, l'app gira solo su questo Mac senza avvisi di Gatekeeper.
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

if [ -n "${SHINOBICAM_SIGN_ID:-}" ]; then
    echo "== Verifica firma"
    codesign --verify --deep --strict --verbose=2 "$APP"
fi

if [ -n "${SHINOBICAM_NOTARY_PROFILE:-}" ]; then
    [ -n "${SHINOBICAM_SIGN_ID:-}" ] || { echo "La notarizzazione richiede SHINOBICAM_SIGN_ID" >&2; exit 1; }
    echo "== Notarizzazione (qualche minuto)"
    ditto -c -k --keepParent "$APP" dist/notarize.zip
    xcrun notarytool submit dist/notarize.zip --keychain-profile "$SHINOBICAM_NOTARY_PROFILE" --wait
    rm dist/notarize.zip
    xcrun stapler staple "$APP"
    spctl --assess --type execute --verbose=2 "$APP"   # "accepted, source=Notarized Developer ID"
fi

echo "== Pacchetto"
ditto -c -k --keepParent "$APP" dist/ShinobiCam-macos-arm64.zip
echo "Fatto: $APP  e  dist/ShinobiCam-macos-arm64.zip"
