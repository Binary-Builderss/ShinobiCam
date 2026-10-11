"""Kawarimi no Jutsu state machine and compositing (independent of gesture detection)."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np

from .config import LOG_SPRITE_RELPATH, resource_path
from .smoke_renderer import SmokeRenderer

log = logging.getLogger(__name__)


class Phase(str, Enum):
    IDLE = "IDLE"
    SMOKE_IN = "SMOKE_IN"
    SUBSTITUTION = "SUBSTITUTION"
    SMOKE_OUT = "SMOKE_OUT"
    COOLDOWN = "COOLDOWN"


@dataclass
class Timing:
    smoke_in: float = 0.5
    substitution: float = 2.0
    smoke_out: float = 0.5
    cooldown: float = 4.0


@dataclass
class Anchor:
    cloud_center: tuple[float, float]
    cloud_radii: tuple[float, float]
    log_center: tuple[float, float]
    log_height: float


def anchor_for(shape, person_box=None, hands_center=None) -> Anchor:
    """Where to put the cloud and the log: person bbox (from the plate) > hands (seal at chest) > frame center."""
    H, W = shape[:2]
    if person_box is not None:
        x, y, w, h = person_box
        cx = x + w / 2
        return Anchor((cx, y + h / 2), (min(max(0.62 * w, 0.2 * W), 0.6 * W), min(max(0.6 * h, 0.3 * H), 0.65 * H)),
                      (cx, y + 0.62 * h), float(np.clip(0.85 * h, 0.4 * H, 0.85 * H)))
    cx = hands_center[0] if hands_center is not None else W / 2
    torso_y = hands_center[1] + 0.05 * H if hands_center is not None else 0.65 * H
    return Anchor((cx, 0.55 * H), (0.33 * W, 0.55 * H), (cx, min(torso_y, 0.8 * H)), 0.6 * H)


# ---------------------------------------------------------------- sprites

def make_log_sprite(height: int = 450, seed: int = 7) -> np.ndarray:
    """Original cel-shaded substitution log (BGRA), drawn procedurally at 2x then downsampled."""
    rng = np.random.default_rng(seed)
    S = 2
    H, W = height * S, int(height * 0.62) * S
    img = np.zeros((H, W, 3), np.uint8)
    mask = np.zeros((H, W), np.uint8)
    cx, rb = int(W * 0.46), int(W * 0.3)
    top, bottom, ery = int(H * 0.12), int(H * 0.94), int(W * 0.11)

    # cylinder body, 3-tone cel shading lit from the upper left
    xs = np.arange(W)
    u = np.clip((xs - cx) / rb, -1, 1)
    inten = np.sqrt(1 - u ** 2) * 0.85 - u * 0.45
    tone = np.select([inten > 0.75, inten > 0.3], [1.0, 0.78], 0.55)
    bark = np.array([38, 78, 128], np.float32)
    body = np.zeros_like(mask)
    cv2.rectangle(body, (cx - rb, top), (cx + rb, bottom), 255, -1)
    cv2.ellipse(body, (cx, bottom), (rb, ery), 0, 0, 180, 255, -1)
    cols = (bark[None, :] * tone[:, None]).astype(np.uint8)
    img[body > 0] = np.broadcast_to(cols[None, :, :], (H, W, 3))[body > 0]
    mask |= body

    # bark grooves and a knot, clipped to the body
    grooves = np.zeros_like(img)
    gmask = np.zeros_like(mask)
    for i in range(9):
        x0 = cx - rb + (i + 0.5) * 2 * rb / 9 + rng.uniform(-8, 8)
        ph, amp = rng.uniform(0, 6.28), rng.uniform(4, 10)
        pts = np.array([[x0 + amp * math.sin(y / 45 + ph), y] for y in range(top + ery, bottom + ery, 12)], np.int32)
        cv2.polylines(gmask, [pts], False, 255, 6, cv2.LINE_AA)
    kx, ky = cx - rb // 3, int(H * 0.55)
    cv2.ellipse(gmask, (kx, ky), (int(rb * 0.16), int(rb * 0.26)), 0, 0, 360, 255, 8, cv2.LINE_AA)
    grooves[:] = (18, 38, 66)
    sel = (gmask > 0) & (body > 0)
    img[sel] = grooves[sel]

    # branch stub on the right
    by = int(H * 0.38)
    stub = np.array([[cx + rb - 10, by], [cx + rb + int(rb * 0.55), by - int(rb * 0.35)],
                     [cx + rb + int(rb * 0.62), by - int(rb * 0.05)], [cx + rb - 10, by + int(rb * 0.4)]], np.int32)
    cv2.fillPoly(img, [stub], (30, 64, 110), cv2.LINE_AA)
    cv2.fillPoly(mask, [stub], 255)
    sc = (cx + rb + int(rb * 0.585), by - int(rb * 0.2))
    cv2.ellipse(img, sc, (int(rb * 0.1), int(rb * 0.17)), -20, 0, 360, (120, 180, 222), -1, cv2.LINE_AA)
    cv2.ellipse(img, sc, (int(rb * 0.1), int(rb * 0.17)), -20, 0, 360, (25, 25, 35), 5, cv2.LINE_AA)
    cv2.ellipse(mask, sc, (int(rb * 0.1), int(rb * 0.17)), -20, 0, 360, 255, -1)

    # cut top face with growth rings
    cv2.ellipse(img, (cx, top), (rb, ery), 0, 0, 360, (125, 185, 228), -1, cv2.LINE_AA)
    cv2.ellipse(mask, (cx, top), (rb, ery), 0, 0, 360, 255, -1)
    for k in (0.78, 0.55, 0.33):
        cv2.ellipse(img, (cx + 4, top), (int(rb * k), int(ery * k)), 0, 0, 360, (85, 145, 195), 4, cv2.LINE_AA)
    cv2.ellipse(img, (cx, top), (rb, ery), 0, 0, 360, (25, 25, 35), 7, cv2.LINE_AA)

    # thick cel outline behind everything
    outline = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))
    edge = (outline > 0) & (mask == 0)
    img[edge] = (25, 25, 35)
    bgra = np.dstack([img, outline])
    return cv2.resize(bgra, (W // S, H // S), interpolation=cv2.INTER_AREA)


def load_log_sprite(custom: str = "") -> tuple[np.ndarray, str]:
    """(BGRA sprite, source description). Falls back from custom PNG to bundled asset to procedural."""
    for path in ([Path(custom)] if custom else []) + [resource_path(LOG_SPRITE_RELPATH)]:
        try:
            img = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_UNCHANGED)  # unicode-safe on Windows
        except (OSError, ValueError):
            img = None
        if img is None or img.ndim != 3 or min(img.shape[:2]) < 8:
            log.warning("sprite tronco non caricabile: %s", path)
            continue
        if img.shape[2] == 3:
            img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
        return img, str(path)
    return make_log_sprite(), "procedurale"


def overlay_rgba(dst: np.ndarray, src: np.ndarray, cx: float, cy: float) -> None:
    """Alpha-blend BGRA `src` centered at (cx, cy) into BGR `dst` in place, clipped to the frame."""
    h, w = src.shape[:2]
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    dx0, dy0 = max(x0, 0), max(y0, 0)
    dx1, dy1 = min(x0 + w, dst.shape[1]), min(y0 + h, dst.shape[0])
    if dx0 >= dx1 or dy0 >= dy1:
        return
    s = src[dy0 - y0:dy1 - y0, dx0 - x0:dx1 - x0]
    a = s[:, :, 3:4].astype(np.float32) / 255.0
    roi = dst[dy0:dy1, dx0:dx1]
    roi[:] = (s[:, :, :3] * a + roi * (1.0 - a)).astype(np.uint8)


def rotate_rgba(img: np.ndarray, angle_deg: float) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    c, s = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * s + w * c) + 2, int(h * c + w * s) + 2
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(img, m, (nw, nh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))


# ---------------------------------------------------------------- engine

class EffectEngine:
    """IDLE -> SMOKE_IN -> SUBSTITUTION -> SMOKE_OUT -> COOLDOWN -> IDLE. Times are passed in (testable)."""

    def __init__(self, log_sprite: np.ndarray, timing: Timing | None = None, smoke: SmokeRenderer | None = None):
        self.timing = timing or Timing()
        self.smoke = smoke or SmokeRenderer()
        self.log_sprite = log_sprite
        self.phase = Phase.IDLE
        self.simplified = False      # True when the run had no background plate
        self._t0 = 0.0
        self._anchor: Anchor | None = None
        self._sprite: np.ndarray | None = None
        self._out_burst = False

    # times relative to the trigger
    def _marks(self):
        t = self.timing
        t1 = t.smoke_in
        t2 = t1 + t.substitution
        return t1, t2, t2 + 0.5 * t.smoke_out, t2 + t.smoke_out, t2 + t.smoke_out + t.cooldown

    def trigger(self, now: float, anchor: Anchor) -> bool:
        """Start the jutsu. Ignored (False) unless IDLE: no double activation mid-animation or in cooldown."""
        self.update(now)
        if self.phase is not Phase.IDLE:
            return False
        self._t0, self._anchor, self._out_burst = now, anchor, False
        h = max(int(anchor.log_height), 16)
        sh, sw = self.log_sprite.shape[:2]
        self._sprite = cv2.resize(self.log_sprite, (max(int(sw * h / sh), 8), h), interpolation=cv2.INTER_AREA)
        self.smoke.burst(anchor.cloud_center, anchor.cloud_radii, now, self.timing.smoke_in, 0.9)
        self.phase = Phase.SMOKE_IN
        return True

    def reset(self) -> None:
        self.phase = Phase.IDLE
        self.smoke.clear()

    def update(self, now: float) -> Phase:
        if self.phase is Phase.IDLE:
            return self.phase
        t1, t2, _, t3, t4 = self._marks()
        e = now - self._t0
        if e >= t2 and not self._out_burst:
            self._out_burst = True
            a = self._anchor
            self.smoke.burst(a.cloud_center, a.cloud_radii, self._t0 + t2, 0.5 * self.timing.smoke_out, 0.8)
        self.phase = (Phase.SMOKE_IN if e < t1 else Phase.SUBSTITUTION if e < t2 else
                      Phase.SMOKE_OUT if e < t3 else Phase.COOLDOWN if e < t4 else Phase.IDLE)
        return self.phase

    def substituted(self, now: float) -> bool:
        """Scene swap happens only while the smoke is at full opacity."""
        if self.phase is Phase.IDLE:
            return False
        t1, _, t_back, _, _ = self._marks()
        return t1 <= now - self._t0 < t_back

    def render(self, frame: np.ndarray, now: float, plate: np.ndarray | None = None) -> np.ndarray:
        """Output frame for `now`. Without a plate the person stays visible (simplified mode)."""
        self.update(now)
        out = frame
        if self.substituted(now):
            self.simplified = plate is None
            out = (plate if plate is not None else frame).copy()
            t = now - self._t0 - self.timing.smoke_in
            a = self._anchor
            drop = -0.12 * a.log_height * max(0.0, 1 - t / 0.25) ** 2
            wobble = 9.0 * math.exp(-t / 0.35) * math.sin(2 * math.pi * 2.5 * t)
            bob = -0.03 * a.log_height * math.exp(-t / 0.25) * abs(math.sin(2 * math.pi * 2.5 * t))
            overlay_rgba(out, rotate_rgba(self._sprite, 4.0 + wobble), a.log_center[0], a.log_center[1] + drop + bob)
        return self.smoke.render(out, now)
