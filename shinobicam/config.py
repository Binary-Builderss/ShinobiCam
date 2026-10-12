"""Settings, user data paths and bundled-resource lookup (dev and PyInstaller)."""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ShinobiCam"
log = logging.getLogger(__name__)

RESOLUTIONS = {"1280x720": (1280, 720), "640x360": (640, 360), "640x480": (640, 480)}
FPS_CHOICES = (30, 24, 15)
BACKENDS = ("obs", "unitycapture") if sys.platform == "win32" else ("obs",)
MODEL_RELPATH = "models/hand_landmarker.task"
LOG_SPRITE_RELPATH = "assets/log.png"


def resource_path(relpath: str) -> Path:
    """Read-only bundled file: next to the package in dev, inside _MEIPASS when frozen."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
    return Path(base) / relpath


def data_dir() -> Path:
    """Writable per-user folder: %APPDATA%\\ShinobiCam (Windows), ~/Library/Application Support/ShinobiCam (macOS)."""
    root = os.environ.get("SHINOBICAM_HOME")
    if root:
        d = Path(root)
    elif os.environ.get("APPDATA"):
        d = Path(os.environ["APPDATA"]) / APP_NAME
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        d = Path.home() / ".shinobicam"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Settings:
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    backend: str = "obs"
    recognition_enabled: bool = True
    threshold: float = 0.6        # minimum gesture confidence (0..1)
    hold_ms: int = 300            # gesture must persist this long
    cooldown_s: float = 4.0
    smoke_ms: int = 500
    substitution_ms: int = 2000
    log_image: str = ""           # custom PNG, empty = bundled log
    debug: bool = False
    autostart: bool = False       # start the virtual camera when the app opens

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or data_dir() / "settings.json"
        s = cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return s
        except (OSError, ValueError) as e:
            log.warning("settings ignorati (%s): %s", path, e)
            return s
        for f in dataclasses.fields(cls):
            v = raw.get(f.name)
            default = getattr(s, f.name)
            if isinstance(v, type(default)) or (isinstance(default, float) and type(v) is int):
                setattr(s, f.name, type(default)(v))
        if s.backend not in BACKENDS:
            s.backend = "obs"
        return s

    def save(self, path: Path | None = None) -> None:
        path = path or data_dir() / "settings.json"
        path.write_text(json.dumps(dataclasses.asdict(self), indent=2), encoding="utf-8")
