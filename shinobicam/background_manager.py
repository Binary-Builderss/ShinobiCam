"""Clean background plate (scene without the person) and person localisation by difference."""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)


class BackgroundManager:
    COUNTDOWN_S = 5.0
    CAPTURE_S = 1.5

    def __init__(self, path: Path):
        self.path = Path(path)
        self.plate: np.ndarray | None = None
        self._capture_from: float | None = None
        self._acc: np.ndarray | None = None
        self._n = 0
        img = cv2.imread(str(self.path)) if self.path.is_file() else None
        if img is not None:
            self.plate = img

    # ------------------------------------------------------------ capture
    @property
    def capturing(self) -> bool:
        return self._capture_from is not None

    def start_capture(self, now: float) -> None:
        self._capture_from = now + self.COUNTDOWN_S
        self._acc, self._n = None, 0

    def cancel_capture(self) -> None:
        self._capture_from = None

    def feed(self, frame: np.ndarray, now: float) -> str | None:
        """Call with every live frame. Returns 'done' when a new plate was stored, else None."""
        if self._capture_from is None or now < self._capture_from:
            return None
        if self._acc is None or self._acc.shape != frame.shape:
            self._acc, self._n = np.zeros(frame.shape, np.float32), 0
        self._acc += frame  # running mean: no blocking median over a frame stack
        self._n += 1
        if now < self._capture_from + self.CAPTURE_S:
            return None
        self.plate = (self._acc / self._n).round().astype(np.uint8)
        self._capture_from, self._acc = None, None
        if not cv2.imwrite(str(self.path), self.plate):
            log.error("salvataggio sfondo fallito: %s", self.path)
        return "done"

    def message(self, now: float) -> str:
        if self._capture_from is None:
            return ""
        if now < self._capture_from:
            return f"Esci dall'inquadratura... {self._capture_from - now:.0f}"
        return "Acquisizione sfondo..."

    def clear(self) -> None:
        self.plate = None
        self.path.unlink(missing_ok=True)

    # ------------------------------------------------------------ use
    def plate_for(self, shape) -> np.ndarray | None:
        """The plate only if it matches the current resolution (otherwise recalibration is needed)."""
        if self.plate is None or self.plate.shape != tuple(shape):
            return None
        return self.plate

    def person_bbox(self, frame: np.ndarray, thresh: int = 35) -> tuple[int, int, int, int] | None:
        """(x, y, w, h) of the largest region differing from the plate."""
        plate = self.plate_for(frame.shape)
        if plate is None:
            return None
        s = 4
        small = cv2.resize(frame, (frame.shape[1] // s, frame.shape[0] // s), interpolation=cv2.INTER_AREA)
        bg = cv2.resize(plate, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_AREA)
        diff = cv2.absdiff(small, bg).max(axis=2)
        mask = (cv2.GaussianBlur(diff, (5, 5), 0) > thresh).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) < 0.02 * mask.size:
            return None
        x, y, w, h = cv2.boundingRect(c)
        return x * s, y * s, w * s, h * s
