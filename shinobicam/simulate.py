"""Offline simulation of the jutsu (no webcam, no Teams): renders a video file.

    python -m shinobicam.simulate out.mp4 [--background bg.png --person person.png] [--no-plate]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from .background_manager import BackgroundManager
from .effect_engine import EffectEngine, Timing, anchor_for, load_log_sprite


def synthetic_scene(w: int = 1280, h: int = 720):
    """A room (plate) and the same room with a stylised person in front."""
    bg = np.zeros((h, w, 3), np.uint8)
    bg[:] = np.linspace(170, 120, h, dtype=np.uint8)[:, None, None] * np.array([1.0, 0.95, 0.85])
    cv2.rectangle(bg, (int(w * .08), int(h * .12)), (int(w * .3), int(h * .55)), (90, 130, 60), -1)    # window/plant
    cv2.rectangle(bg, (int(w * .72), int(h * .2)), (int(w * .95), int(h * .9)), (60, 90, 140), -1)     # bookshelf
    for i in range(5):
        y = int(h * (.28 + i * .13))
        cv2.line(bg, (int(w * .72), y), (int(w * .95), y), (40, 60, 95), 6)
    person = bg.copy()
    cv2.ellipse(person, (w // 2, int(h * .95)), (int(w * .22), int(h * .42)), 0, 180, 360, (70, 50, 160), -1)   # torso
    cv2.circle(person, (w // 2, int(h * .36)), int(h * .14), (140, 170, 215), -1)                              # head
    cv2.ellipse(person, (w // 2, int(h * .27)), (int(h * .15), int(h * .08)), 0, 180, 360, (30, 30, 40), -1)   # hair
    return bg, person


def run(out: Path, bg: np.ndarray, person: np.ndarray, use_plate: bool, fps: int = 30, seconds: float = 6.0,
        frames_dir: Path | None = None) -> None:
    h, w = person.shape[:2]
    bm = BackgroundManager(out.with_suffix(".plate.png"))
    bm.plate = bg if use_plate else None
    sprite, _ = load_log_sprite()
    engine = EffectEngine(sprite, Timing())
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(int(seconds * fps)):
        now = i / fps
        if i == fps // 2:
            engine.trigger(now, anchor_for(person.shape, bm.person_bbox(person)))
        frame = engine.render(person, now, bm.plate_for(person.shape))
        cv2.putText(frame, f"{now:4.2f}s {engine.phase.value}", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        writer.write(frame)
        if frames_dir is not None and i % 3 == 0:
            frames_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(frames_dir / f"f{i:03d}.jpg"), frame)
    writer.release()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    ap.add_argument("--background", type=Path)
    ap.add_argument("--person", type=Path)
    ap.add_argument("--no-plate", action="store_true", help="modalita' semplificata (sfondo non calibrato)")
    ap.add_argument("--frames", type=Path, help="salva anche un JPG ogni 3 frame in questa cartella")
    a = ap.parse_args(argv)
    if a.background and a.person:
        bg, person = cv2.imread(str(a.background)), cv2.imread(str(a.person))
        if bg is None or person is None or bg.shape != person.shape:
            ap.error("background e person devono essere immagini leggibili della stessa risoluzione")
    else:
        bg, person = synthetic_scene()
    run(a.out, bg, person, not a.no_plate, frames_dir=a.frames)
    print(f"scritto {a.out}")


if __name__ == "__main__":
    main()
