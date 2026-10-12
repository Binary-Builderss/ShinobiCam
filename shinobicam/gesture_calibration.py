"""Guided seal recording: countdown, then collect descriptors for a few seconds."""
from __future__ import annotations

import numpy as np

from .gesture_detector import GestureProfile, dedupe_hands, descriptor, to_aspect


class GestureCalibrator:
    LOST_S = 0.5  # no usable hands for this long while recording -> warn the user live

    def __init__(self, now: float, countdown_s: float = 3.0, record_s: float = 4.0):
        self.t_record = now + countdown_s
        self.t_end = self.t_record + record_s
        self.descriptors: list[np.ndarray] = []
        self.frames_seen = 0
        self.t_seen = self.t_record
        self.snapshot: tuple[np.ndarray, list[np.ndarray]] | None = None  # (frame, hands) from the first half

    def done(self, now: float) -> bool:
        return now >= self.t_end

    def feed(self, hands: list[np.ndarray], aspect: float, now: float, frame: np.ndarray | None = None) -> None:
        if not self.t_record <= now < self.t_end:
            return
        self.frames_seen += 1
        d = descriptor(dedupe_hands(to_aspect(hands, aspect)))
        if d is not None:
            self.descriptors.append(d)
            self.t_seen = now
            if frame is not None and (self.snapshot is None or self.progress(now) < 0.5):
                self.snapshot = (frame, hands)  # mid-recording pose: settled, not the first twitch

    def hands_lost(self, now: float) -> bool:
        return self.t_record <= now < self.t_end and now - self.t_seen > self.LOST_S

    def remaining(self, now: float) -> float | None:
        """Seconds left before recording starts, None once recording."""
        return self.t_record - now if now < self.t_record else None

    def progress(self, now: float) -> float:
        span = self.t_end - self.t_record
        return min(max((now - self.t_record) / span, 0.0), 1.0)

    def message(self, now: float) -> str:
        if now < self.t_record:
            return f"Prepara il sigillo... {self.t_record - now:.0f}"
        if self.hands_lost(now):
            return "Non vedo le mani: tienile dentro l'inquadratura"
        if now < self.t_end:
            return f"REC sigillo {self.t_end - now:.1f}s - campioni {len(self.descriptors)}"
        return "Registrazione completata"

    def result(self, name: str = "Sigillo") -> GestureProfile:
        """Raises ValueError (Italian message) when too few frames had hands visible."""
        return GestureProfile.build(self.descriptors, name)
