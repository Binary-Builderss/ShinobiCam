"""Anime-style smoke cloud: puffs rendered on a low-res alpha map, shaded, then composited once."""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Puff:
    x: float
    y: float
    vx: float
    vy: float
    r: float          # full radius (output pixels)
    t0: float         # spawn time
    peak: float       # absolute time of full size
    end: float        # absolute time fully faded
    start_scale: float = 0.3

    def state(self, now: float):
        """(x, y, radius, alpha) at `now`, or None when not alive."""
        if now < self.t0 or now >= self.end:
            return None
        if now < self.peak:
            k = (now - self.t0) / max(self.peak - self.t0, 1e-6)
            k = 1 - (1 - k) ** 3                      # ease-out growth
            return self.x, self.y, self.r * (self.start_scale + (1 - self.start_scale) * k), 1.0
        u = (now - self.peak) / max(self.end - self.peak, 1e-6)
        drift = (now - self.peak)
        return (self.x + self.vx * drift, self.y + self.vy * drift,
                self.r * (1 + 0.35 * u), (1 - u) ** 1.6)


class SmokeRenderer:
    """Bursts are guaranteed opaque inside their ellipse at peak time (dense puff grid)."""

    SCALE = 4  # alpha map resolution divisor

    def __init__(self, rng: np.random.Generator | None = None):
        self.rng = rng or np.random.default_rng()
        self.puffs: list[Puff] = []

    def clear(self) -> None:
        self.puffs.clear()

    def active(self, now: float) -> bool:
        return any(p.end > now for p in self.puffs)

    def burst(self, center, radii, now: float, peak_s: float, fade_s: float) -> None:
        cx, cy = center
        rx, ry = radii
        rng = self.rng
        s = 0.33 * min(rx, ry)            # grid spacing; puff radius 1.0*s covers the gaps fully
        peak = now + peak_s
        reach = 1.0 + 0.6 * s / min(rx, ry)  # grid slightly past the rim so the rim itself is covered
        for gy in np.arange(-ry * reach, ry * reach + 1e-6, s):
            for gx in np.arange(-rx * reach, rx * reach + 1e-6, s):
                if math.hypot(gx / rx, gy / ry) > reach:
                    continue
                x = cx + gx + rng.uniform(-0.06, 0.06) * s
                y = cy + gy + rng.uniform(-0.06, 0.06) * s
                d = math.hypot(gx / rx, gy / ry) + 1e-6
                speed = rng.uniform(0.15, 0.45) * min(rx, ry)
                # outer puffs appear later: the cloud grows from the centre instead of popping in as dots
                self.puffs.append(Puff(x, y, speed * gx / rx / d, speed * gy / ry / d - 0.2 * speed,
                                       s * rng.uniform(1.0, 1.15), now + 0.55 * peak_s * min(d, 1.0), peak,
                                       peak + fade_s * rng.uniform(0.75, 1.25), start_scale=0.15))
        # Scalloped rim: the puffy anime silhouette.
        n = 18
        for i in range(n):
            a = 2 * math.pi * (i + rng.uniform(-0.2, 0.2)) / n
            ex, ey = math.cos(a), math.sin(a)
            speed = rng.uniform(0.3, 0.7) * min(rx, ry)
            self.puffs.append(Puff(cx + rx * ex, cy + ry * ey, speed * ex, speed * ey - 0.2 * speed,
                                   s * rng.uniform(0.9, 1.4), now + 0.5 * peak_s, peak - 0.2 * peak_s * rng.uniform(0, 1),
                                   peak + fade_s * rng.uniform(0.5, 1.0), start_scale=0.1))
        # Wisps flying out of the cloud.
        for _ in range(14):
            a = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(0.8, 1.6) * min(rx, ry)
            self.puffs.append(Puff(cx + 0.8 * rx * math.cos(a), cy + 0.8 * ry * math.sin(a),
                                   speed * math.cos(a), speed * math.sin(a), s * rng.uniform(0.3, 0.6),
                                   now + peak_s * 0.5, peak, peak + fade_s * rng.uniform(0.4, 0.9), start_scale=0.5))

    def alpha_map(self, shape, now: float) -> np.ndarray | None:
        """Low-res float32 alpha (H/SCALE, W/SCALE) or None when nothing is visible."""
        self.puffs = [p for p in self.puffs if p.end > now]
        h, w = shape[0] // self.SCALE, shape[1] // self.SCALE
        mask = np.zeros((h, w), np.float32)
        drawn = False
        for p in self.puffs:
            st = p.state(now)
            if st is None:
                continue
            x, y, r, a = st[0] / self.SCALE, st[1] / self.SCALE, st[2] / self.SCALE, st[3]
            x0, x1 = max(int(x - r) - 1, 0), min(int(x + r) + 2, w)
            y0, y1 = max(int(y - r) - 1, 0), min(int(y + r) + 2, h)
            if x0 >= x1 or y0 >= y1 or a <= 0.003:
                continue
            yy, xx = np.ogrid[y0:y1, x0:x1]
            d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
            edge = max(1.0, 0.12 * r)
            disc = np.clip((r - d) / edge, 0.0, 1.0) * a
            np.maximum(mask[y0:y1, x0:x1], disc.astype(np.float32), out=mask[y0:y1, x0:x1])
            drawn = True
        return mask if drawn else None

    def render(self, frame: np.ndarray, now: float) -> np.ndarray:
        mask = self.alpha_map(frame.shape, now)
        if mask is None:
            return frame
        h, w = frame.shape[:2]
        # Bright core, grey rims, dark cel outline.
        k = max(3, (min(mask.shape) // 6) | 1)
        shade = cv2.GaussianBlur(mask, (k, k), 0)
        color = 170.0 + 85.0 * np.clip(shade * 1.25, 0, 1)
        solid = (mask > 0.5).astype(np.uint8)
        outline = solid - cv2.erode(solid, np.ones((3, 3), np.uint8))
        color[outline > 0] = 105.0
        alpha = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
        color = cv2.resize(color.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
        gray = np.clip(color, 0, 255).astype(np.uint8)
        smoke = cv2.merge([gray, gray, np.clip(color + 4, 0, 255).astype(np.uint8)])
        return cv2.blendLinear(smoke, frame, alpha, 1.0 - alpha)
