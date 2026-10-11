"""Physical webcam: enumeration, capture thread with auto-reconnect, latest-frame slot."""
from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable

import cv2
import numpy as np

log = logging.getLogger(__name__)

VIRTUAL_CAMERA_NAMES = ("obs virtual camera", "unity video capture", "obs-camera")


class LatestFrame:
    """One-slot buffer: writers overwrite, readers only ever see the newest item (no lag build-up)."""

    def __init__(self):
        self._cond = threading.Condition()
        self._item = None
        self._seq = 0
        self._stamp = 0.0

    def put(self, item) -> None:
        with self._cond:
            self._item, self._stamp = item, time.monotonic()
            self._seq += 1
            self._cond.notify_all()

    def get(self, after_seq: int = 0, timeout: float | None = None):
        """Wait for an item newer than `after_seq`. Returns (seq, item), item None on timeout."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._seq > after_seq, timeout):
                return after_seq, None
            return self._seq, self._item

    def peek(self):
        """(seq, item, age_seconds) without waiting."""
        with self._cond:
            return self._seq, self._item, time.monotonic() - self._stamp


def is_virtual(name: str) -> bool:
    return any(v in name.lower() for v in VIRTUAL_CAMERA_NAMES)


def list_cameras(max_probe: int = 5) -> list[tuple[int, str]]:
    """(index, name). On Windows names come from DirectShow (same order as cv2.CAP_DSHOW)."""
    if sys.platform == "win32":
        try:
            from pygrabber.dshow_graph import FilterGraph
            return list(enumerate(FilterGraph().get_input_devices()))
        except Exception as e:  # pygrabber missing or COM failure: fall back to probing
            log.warning("enumerazione DirectShow fallita: %s", e)
    found = []
    for i in range(max_probe):
        cap = _new_capture(i)
        if cap.isOpened():
            found.append((i, f"Webcam {i}"))
        cap.release()
    return found


def _new_capture(index: int) -> cv2.VideoCapture:
    if sys.platform == "win32":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)  # MSMF opens slowly on many webcams
    return cv2.VideoCapture(index)


def open_capture(index: int, width: int, height: int, fps: int):
    cap = _new_capture(index)
    if not cap.isOpened():
        cap.release()
        return None
    # MJPG lets most USB webcams deliver 720p at 30 FPS (raw YUY2 is often capped at ~10).
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def fit_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Center-crop to the target aspect ratio, then resize (no stretching)."""
    h, w = frame.shape[:2]
    if (w, h) == (width, height):
        return frame
    target = width / height
    if w / h > target:
        cw = int(round(h * target))
        x0 = (w - cw) // 2
        frame = frame[:, x0:x0 + cw]
    else:
        ch = int(round(w / target))
        y0 = (h - ch) // 2
        frame = frame[y0:y0 + ch]
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


class CameraManager:
    """Reads the webcam on its own thread; reconnects automatically when the device is lost."""

    RETRY_S = 1.0
    MAX_FAILED_READS = 15

    def __init__(self, index: int, width: int, height: int, fps: int,
                 opener: Callable = open_capture):
        self.index, self.width, self.height, self.fps = index, width, height, fps
        self.frames = LatestFrame()
        self.status = "ferma"
        self.connected = False
        self._opener = opener
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self.status, self.connected = "ferma", False

    def _set(self, connected: bool, status: str) -> None:
        if status != self.status:
            log.info("webcam %s: %s", self.index, status)
        self.connected, self.status = connected, status

    def _run(self) -> None:
        cap, fails = None, 0
        try:
            while not self._stop.is_set():
                if cap is None:
                    try:
                        cap = self._opener(self.index, self.width, self.height, self.fps)
                    except Exception:
                        log.exception("apertura webcam fallita")
                        cap = None
                    if cap is None:
                        self._set(False, "webcam non disponibile, nuovo tentativo...")
                        self._stop.wait(self.RETRY_S)
                        continue
                    self._set(True, "connessa")
                    fails = 0
                ok, frame = cap.read()
                if not ok or frame is None:
                    fails += 1
                    if fails >= self.MAX_FAILED_READS:
                        self._set(False, "webcam persa, riconnessione...")
                        cap.release()
                        cap = None
                    else:
                        self._stop.wait(0.02)
                    continue
                fails = 0
                self.frames.put(fit_frame(frame, self.width, self.height))
        finally:
            if cap is not None:
                cap.release()
