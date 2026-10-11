"""Guided seal recording: countdown, then collect descriptors for a few seconds."""
from __future__ import annotations

import numpy as np

from .gesture_detector import GestureProfile, dedupe_hands, descriptor, to_aspect


class GestureCalibrator:
    def __init__(self, now: float, countdown_s: float = 3.0, record_s: float = 4.0):
        self.t_record = now + countdown_s
        self.t_end = self.t_record + record_s
        self.descriptors: list[np.ndarray] = []
        self.frames_seen = 0

    def done(self, now: float) -> bool:
        return now >= self.t_end

    def feed(self, hands: list[np.ndarray], aspect: float, now: float) -> None:
        if not self.t_record <= now < self.t_end:
            return
        self.frames_seen += 1
        d = descriptor(dedupe_hands(to_aspect(hands, aspect)))
        if d is not None:
            self.descriptors.append(d)

    def message(self, now: float) -> str:
        if now < self.t_record:
            return f"Prepara il sigillo... {self.t_record - now:.0f}"
        if now < self.t_end:
            return f"REC sigillo {self.t_end - now:.1f}s - campioni {len(self.descriptors)}"
        return "Registrazione completata"

    def result(self, name: str = "Sigillo") -> GestureProfile:
        """Raises ValueError (Italian message) when too few frames had hands visible."""
        return GestureProfile.build(self.descriptors, name)
