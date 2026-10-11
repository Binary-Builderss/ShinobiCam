#!/usr/bin/env bash
# Prepara l'ambiente di sviluppo/build su macOS (Apple Silicon, macOS 13+).
# Uso: ./scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL_URL="https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
MODEL_SHA="fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
MODEL=models/hand_landmarker.task

[ "$(uname -m)" = "arm64" ] || { echo "Serve un Mac Apple Silicon: mediapipe non pubblica wheel macOS Intel." >&2; exit 1; }

echo "== Python 3.11-3.13 con Tkinter"
PY=""
for c in python3.11 python3.12 python3.13 python3; do
    if command -v "$c" >/dev/null && "$c" -c "import sys, tkinter; assert (3, 11) <= sys.version_info[:2] <= (3, 13)" 2>/dev/null; then
        PY="$(command -v "$c")"; break
    fi
done
[ -n "$PY" ] || { echo "Python 3.11 non trovato (con Tkinter). Installa da https://www.python.org/downloads/macos/" >&2; exit 1; }
echo "Uso $PY"

echo "== Ambiente virtuale .venv"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

echo "== Modello MediaPipe Hand Landmarker"
if [ ! -f "$MODEL" ]; then
    mkdir -p models
    curl -fsSL -o "$MODEL" "$MODEL_URL"
fi
if [ "$(shasum -a 256 "$MODEL" | cut -d' ' -f1)" != "$MODEL_SHA" ]; then
    rm -f "$MODEL"; echo "Checksum del modello errato: file rimosso, rilancia lo script." >&2; exit 1
fi

echo "== Webcam virtuale (OBS)"
if [ -d "/Applications/OBS.app" ]; then
    echo "OBS trovato. Se non l'hai gia' fatto: apri OBS, 'Avvia videocamera virtuale', consenti l'estensione, poi chiudi OBS."
else
    echo "ATTENZIONE: OBS non trovato. Per inviare il video a Teams installa OBS 30+ da https://obsproject.com"
fi
echo "Ambiente pronto. Avvio in sviluppo: .venv/bin/python -m shinobicam"
