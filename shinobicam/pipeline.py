"""Threads: capture (CameraManager) -> inference (hands/gesture) and render/output (effect -> virtual cam).

Inference never blocks output: the render thread always uses the newest camera frame and the
newest gesture result, so a slow model lowers recognition rate, not the FPS seen in Teams.
Engine and background state are touched only by the render thread; other threads send commands.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

import cv2
import numpy as np

from .background_manager import BackgroundManager
from .camera_manager import CameraManager, LatestFrame
from .config import MODEL_RELPATH, Settings, data_dir, resource_path
from .effect_engine import EffectEngine, Phase, Timing, anchor_for, load_log_sprite
from .gesture_calibration import GestureCalibrator
from .gesture_detector import (GestureProfile, GestureTrigger, HandDetector, dedupe_hands, descriptor, draw_hands,
                               to_aspect)
from .virtual_camera import VirtualCamera

log = logging.getLogger(__name__)
PROFILE_FILE = "gesture_profile.json"
STALE_CAMERA_S = 1.0


def placeholder_frame(w: int, h: int, text: str) -> np.ndarray:
    img = np.full((h, w, 3), 30, np.uint8)
    scale = w / 1280
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.2 * scale, 2)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.2 * scale,
                (220, 220, 220), 2, cv2.LINE_AA)
    return img


def put_banner(img: np.ndarray, text: str) -> None:
    cv2.rectangle(img, (0, 0), (img.shape[1], 44), (0, 0, 0), -1)
    cv2.putText(img, text, (14, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 255), 2, cv2.LINE_AA)


class Pipeline:
    def __init__(self, settings: Settings, *, camera_factory: Callable = CameraManager,
                 vcam_factory: Callable = VirtualCamera, detector_factory: Callable = HandDetector,
                 model_path=None, clock: Callable[[], float] = time.monotonic):
        self.settings = settings
        self._camera_factory, self._vcam_factory, self._detector_factory = camera_factory, vcam_factory, detector_factory
        self._model_path = model_path or resource_path(MODEL_RELPATH)
        self.clock = clock
        self.preview = LatestFrame()
        self.events: queue.SimpleQueue = queue.SimpleQueue()   # (level, message) for the UI
        self.profile = GestureProfile.load(data_dir() / PROFILE_FILE)
        self.background = BackgroundManager(data_dir() / "background.png")
        sprite, self.sprite_source = load_log_sprite(settings.log_image)
        self.engine = EffectEngine(sprite, self._timing())
        self.trigger = GestureTrigger()
        self.camera = None
        self.vcam = None
        self.detector = None
        self.recognition_error: str | None = None
        self.fps = 0.0
        self.confidence = 0.0
        self._hands: tuple[float, list[np.ndarray]] = (0.0, [])
        self._calibrator: GestureCalibrator | None = None
        self._commands: queue.SimpleQueue = queue.SimpleQueue()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._last_error = ""

    # ------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def start(self, use_virtual_camera: bool = True) -> None:
        """Raises VirtualCameraError (with an Italian hint) if the virtual camera can't be opened."""
        if self.running:
            self.stop()
        s = self.settings
        self._stop.clear()
        if use_virtual_camera:
            vcam = self._vcam_factory(s.width, s.height, s.fps, s.backend)
            vcam.open()
            self.vcam = vcam
        self.camera = self._camera_factory(s.camera_index, s.width, s.height, s.fps)
        self.camera.start()
        self.recognition_error = None
        try:
            self.detector = self._detector_factory(self._model_path)
        except Exception as e:
            log.exception("riconoscimento mani non disponibile")
            self.recognition_error = str(e)
            self.events.put(("warning", f"Riconoscimento gesti non disponibile:\n{e}\n\nPuoi usare comunque F9."))
        self._threads = [threading.Thread(target=self._render_loop, name="render", daemon=True)]
        if self.detector is not None:
            self._threads.append(threading.Thread(target=self._inference_loop, name="inference", daemon=True))
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        """Safe at any time, including mid-animation: joins workers, releases webcam and virtual camera."""
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)
        self._threads = []
        if self.camera is not None:
            self.camera.stop()
            self.camera = None
        if self.vcam is not None:
            self.vcam.close()
            self.vcam = None
        if self.detector is not None:
            self.detector.close()
            self.detector = None
        self.engine.reset()
        self.background.cancel_capture()
        self._calibrator = None
        self.trigger.reset()
        self.fps = self.confidence = 0.0

    # ------------------------------------------------------------ commands (any thread)
    def trigger_manual(self) -> None:
        self._commands.put(self._fire)

    def reset_effect(self) -> None:
        self._commands.put(lambda frame, now: self.engine.reset())

    def start_background_capture(self) -> None:
        self._commands.put(lambda frame, now: self.background.start_capture(now))

    def clear_background(self) -> None:
        self._commands.put(lambda frame, now: self.background.clear())

    def start_gesture_recording(self) -> bool:
        if self.detector is None:
            return False
        self._calibrator = GestureCalibrator(self.clock())
        return True

    def set_log_sprite(self, path: str) -> str:
        sprite, self.sprite_source = load_log_sprite(path)
        self.engine.log_sprite = sprite  # read only at trigger time
        return self.sprite_source

    def _timing(self) -> Timing:
        s = self.settings
        return Timing(s.smoke_ms / 1000, s.substitution_ms / 1000, s.smoke_ms / 1000, s.cooldown_s)

    def status(self) -> dict:
        return {
            "camera": self.camera.status if self.camera else "ferma",
            "vcam": self.vcam.device if self.vcam else "",
            "fps": self.fps,
            "confidence": self.confidence,
            "holding": self.trigger.holding,
            "phase": self.engine.phase.value,
            "profile": self.profile.name if self.profile else "",
            "background": self.background.plate is not None,
            "recognition_error": self.recognition_error,
        }

    def _report(self, where: str, e: Exception) -> None:
        msg = f"Errore in {where}: {e}"
        log.exception(msg)
        if msg != self._last_error:  # don't flood the UI with the same error every frame
            self._last_error = msg
            self.events.put(("error", msg))

    # ------------------------------------------------------------ render thread
    def _fire(self, frame: np.ndarray, now: float) -> None:
        if self.background.capturing:
            return
        hands_center = None
        t, hands = self._hands
        if hands and now - t < 0.5:
            pts = np.concatenate(hands)
            hands_center = (float(pts[:, 0].mean() * frame.shape[1]), float(pts[:, 1].mean() * frame.shape[0]))
        self.engine.timing = self._timing()
        anchor = anchor_for(frame.shape, self.background.person_bbox(frame), hands_center)
        if self.engine.trigger(now, anchor):
            log.info("jutsu! (%s)", "sfondo calibrato" if self.background.plate_for(frame.shape) is not None
                     else "modalita' semplificata")

    def _render_loop(self) -> None:
        s = self.settings
        period = 1.0 / s.fps
        next_t = self.clock()
        no_cam = placeholder_frame(s.width, s.height, "ShinobiCam - webcam non disponibile")
        t_fps, n_fps = self.clock(), 0
        while not self._stop.is_set():
            try:
                now = self.clock()
                _, frame, age = self.camera.frames.peek()
                live = frame is not None and age < STALE_CAMERA_S
                if not live:
                    frame = no_cam
                while not self._commands.empty():
                    self._commands.get_nowait()(frame, now)
                if live and self.background.feed(frame, now) == "done":
                    self.events.put(("info", "Sfondo acquisito. Ora la sostituzione nasconde completamente la persona."))
                out = self.engine.render(frame, now, self.background.plate_for(frame.shape))
                if self.vcam is not None:
                    try:
                        self.vcam.send(out)
                    except Exception as e:
                        self._report("invio alla webcam virtuale", e)
                        self.vcam.close()
                        self.vcam = None
                self.preview.put(self._decorate(out, now))
                n_fps += 1
                if now - t_fps >= 1.0:
                    self.fps, t_fps, n_fps = n_fps / (now - t_fps), now, 0
            except Exception as e:
                self._report("rendering", e)
            next_t += period
            delay = next_t - self.clock()
            if delay > 0:
                self._stop.wait(delay)
            elif delay < -period:      # running late: drop the backlog instead of accumulating delay
                next_t = self.clock()

    def _decorate(self, out: np.ndarray, now: float) -> np.ndarray:
        """Local preview only: overlays never reach the virtual camera."""
        cal, bg_msg = self._calibrator, self.background.message(now)
        if not (self.settings.debug or cal or bg_msg):
            return out
        img = out.copy()
        if self.settings.debug:
            draw_hands(img, self._hands[1])
            cv2.putText(img, f"conf {self.confidence:.2f} / soglia {self.settings.threshold:.2f}  {self.engine.phase.value}",
                        (14, img.shape[0] - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
        if cal:
            put_banner(img, cal.message(now))
        elif bg_msg:
            put_banner(img, bg_msg)
        return img

    # ------------------------------------------------------------ inference thread
    def _inference_loop(self) -> None:
        seq = 0
        while not self._stop.is_set():
            try:
                seq, frame = self.camera.frames.get(seq, timeout=0.5)
                if frame is None:
                    continue
                now = self.clock()
                hands = self.detector.detect(frame, int(now * 1000))
                self._hands = (now, hands)
                aspect = frame.shape[1] / frame.shape[0]
                cal = self._calibrator
                if cal is not None:
                    cal.feed(hands, aspect, now)
                    if cal.done(now):
                        self._finish_recording(cal)
                    continue
                if not self.settings.recognition_enabled or self.profile is None:
                    self.confidence = 0.0
                    self.trigger.reset()
                    continue
                self.confidence = self.profile.confidence(descriptor(dedupe_hands(to_aspect(hands, aspect))))
                self.trigger.hold_s = self.settings.hold_ms / 1000
                if self.trigger.update(self.confidence >= self.settings.threshold, now) and \
                        self.engine.phase is Phase.IDLE:
                    self._commands.put(self._fire)
            except Exception as e:
                self._report("riconoscimento", e)
                self._stop.wait(0.2)

    def _finish_recording(self, cal: GestureCalibrator) -> None:
        self._calibrator = None
        try:
            profile = cal.result()
        except ValueError as e:
            self.events.put(("error", f"Registrazione del sigillo fallita: {e}.\n"
                                      f"Mani rilevate in {len(cal.descriptors)} frame su {cal.frames_seen}. "
                                      "Migliora l'illuminazione e tieni le mani ben inquadrate."))
            return
        profile.save(data_dir() / PROFILE_FILE)
        self.profile = profile
        self.trigger.reset()
        counts = ", ".join(f"{len(v)} con {n} mano/i" for n, v in sorted(profile.samples.items()))
        self.events.put(("info", f"Sigillo registrato ({counts})."))
