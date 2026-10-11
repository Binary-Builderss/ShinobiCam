"""Hand landmarks (MediaPipe) -> normalized descriptor -> match against a recorded seal profile."""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

WRIST, MIDDLE_MCP = 0, 9
DETECT_WIDTH = 640  # landmarks are normalized, so inference on a smaller frame is enough


class ModelMissingError(RuntimeError):
    pass


# ---------------------------------------------------------------- descriptor

def to_aspect(hands: list[np.ndarray], aspect: float) -> list[np.ndarray]:
    """Normalized image coords (x,y in 0..1) -> isotropic coords (x scaled by width/height)."""
    return [h * np.array([aspect, 1.0]) for h in hands]


def dedupe_hands(hands: list[np.ndarray]) -> list[np.ndarray]:
    """When hands overlap MediaPipe can report the same hand twice: keep one."""
    if len(hands) != 2:
        return hands
    a, b = hands
    size = max(np.linalg.norm(a[MIDDLE_MCP] - a[WRIST]), 1e-6)
    if np.mean(np.linalg.norm(a - b, axis=1)) < 0.25 * size:
        return [a]
    return hands


def descriptor(hands: list[np.ndarray]) -> np.ndarray | None:
    """Translation/scale/rotation invariant vector for 1 or 2 hands of (21, 2) isotropic points.

    Hands are ordered by on-screen wrist x, not by MediaPipe's Left/Right label,
    which flips unpredictably when the hands cross in a seal.
    """
    if not hands:
        return None
    hands = sorted(hands, key=lambda h: h[WRIST, 0])
    pts = np.concatenate(hands).astype(np.float64)
    pts -= pts.mean(axis=0)
    up = sum(h[MIDDLE_MCP] - h[WRIST] for h in hands)
    theta = math.atan2(up[1], up[0])
    d = -math.pi / 2 - theta  # rotate "up" onto screen-up (0, -1)
    c, s = math.cos(d), math.sin(d)
    pts = pts @ np.array([[c, s], [-s, c]])
    rms = math.sqrt(float(np.mean(np.sum(pts ** 2, axis=1))))
    if rms < 1e-9:
        return None
    return (pts / rms).ravel()


def distance(a: np.ndarray, b: np.ndarray) -> float:
    """Mean per-landmark displacement, in units of the hand-cluster radius."""
    return float(np.linalg.norm(a - b) / math.sqrt(a.size / 2))


# ---------------------------------------------------------------- profile

@dataclass
class GestureProfile:
    """Recorded seal: samples grouped by visible hand count (2 normally, 1 when the hands overlap)."""
    name: str
    samples: dict[int, np.ndarray] = field(default_factory=dict)
    tolerance: float = 0.2

    MIN_SAMPLES = 8
    MIN_TOL, MAX_TOL = 0.12, 0.35

    @classmethod
    def build(cls, descriptors: list[np.ndarray], name: str = "Sigillo") -> "GestureProfile":
        groups: dict[int, list[np.ndarray]] = {}
        for d in descriptors:
            groups.setdefault(d.size // 42, []).append(d)
        samples = {n: np.array(v) for n, v in groups.items() if len(v) >= cls.MIN_SAMPLES}
        if not samples:
            raise ValueError(f"Servono almeno {cls.MIN_SAMPLES} campioni con le mani visibili")
        spread = []
        for arr in samples.values():
            centroid = arr.mean(axis=0)
            spread += [distance(x, centroid) for x in arr]
        tol = float(np.clip(3.0 * float(np.median(spread)), cls.MIN_TOL, cls.MAX_TOL))
        return cls(name, samples, tol)

    def confidence(self, desc: np.ndarray | None) -> float:
        """1.0 = identical to a recorded sample, ~0.6 at `tolerance`, -> 0 for other poses."""
        if desc is None:
            return 0.0
        arr = self.samples.get(desc.size // 42)
        if arr is None:
            return 0.0
        dmin = float(np.min(np.linalg.norm(arr - desc, axis=1)) / math.sqrt(desc.size / 2))
        return math.exp(-0.5 * (dmin / self.tolerance) ** 2)

    def save(self, path: Path) -> None:
        data = {"name": self.name, "tolerance": self.tolerance,
                "samples": {str(n): arr.round(5).tolist() for n, arr in self.samples.items()}}
        path.write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "GestureProfile | None":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            samples = {int(n): np.array(v, dtype=np.float64) for n, v in data["samples"].items()}
            if not samples or any(a.ndim != 2 or a.shape[1] != int(n) * 42 for n, a in samples.items()):
                raise ValueError("forma campioni non valida")
            return cls(str(data["name"]), samples, float(data["tolerance"]))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning("profilo gesto non valido (%s): %s", path, e)
            return None


# ---------------------------------------------------------------- temporal filter

class GestureTrigger:
    """Fires once when the match persists for `hold_s`; re-arms only after the gesture is released.

    Dropouts shorter than `grace_s` (a frame where the hands were missed) don't reset the hold.
    """

    def __init__(self, hold_s: float = 0.3, grace_s: float = 0.2):
        self.hold_s, self.grace_s = hold_s, grace_s
        self.reset()

    def reset(self) -> None:
        self._start = self._last = None
        self._fired = False

    @property
    def holding(self) -> bool:
        return self._start is not None

    def update(self, matched: bool, now: float) -> bool:
        if matched:
            if self._start is None:
                self._start = now
            self._last = now
            if not self._fired and now - self._start >= self.hold_s:
                self._fired = True
                return True
        elif self._last is not None and now - self._last > self.grace_s:
            self.reset()
        return False


# ---------------------------------------------------------------- MediaPipe

class HandDetector:
    """MediaPipe Hand Landmarker in VIDEO mode, up to two hands, runs fully offline."""

    def __init__(self, model_path: Path, min_confidence: float = 0.5):
        model_path = Path(model_path)
        if not model_path.is_file():
            raise ModelMissingError(f"Modello MediaPipe non trovato: {model_path}")
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self._mp = mp
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=model_path.read_bytes()),  # non-ASCII paths safe
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=min_confidence,
            min_hand_presence_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(opts)
        self._last_ts = -1

    def detect(self, frame_bgr: np.ndarray, ts_ms: int) -> list[np.ndarray]:
        """List of (21, 2) arrays in normalized image coordinates."""
        h, w = frame_bgr.shape[:2]
        if w > DETECT_WIDTH:
            frame_bgr = cv2.resize(frame_bgr, (DETECT_WIDTH, round(h * DETECT_WIDTH / w)), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        ts_ms = max(int(ts_ms), self._last_ts + 1)  # VIDEO mode needs strictly increasing timestamps
        self._last_ts = ts_ms
        result = self._landmarker.detect_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb), ts_ms)
        return [np.array([[p.x, p.y] for p in hand], dtype=np.float64) for hand in result.hand_landmarks]

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None


HAND_CONNECTIONS = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
                    (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17))


def draw_hands(frame: np.ndarray, hands: list[np.ndarray]) -> None:
    """Debug overlay (local preview only)."""
    h, w = frame.shape[:2]
    for i, hand in enumerate(hands):
        color = (0, 220, 255) if i == 0 else (255, 160, 0)
        pts = [(int(x * w), int(y * h)) for x, y in hand]
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, pts[a], pts[b], color, 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(frame, p, 3, (255, 255, 255), -1, cv2.LINE_AA)
