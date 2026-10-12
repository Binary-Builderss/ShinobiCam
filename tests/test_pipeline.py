import functools
import threading
import time

import numpy as np
import pytest

import shinobicam.pipeline as pl
from handgen import seal
from shinobicam.camera_manager import LatestFrame
from shinobicam.config import Settings
from shinobicam.effect_engine import Phase
from shinobicam.gesture_detector import GestureProfile, ModelMissingError, descriptor, dedupe_hands, to_aspect
from shinobicam.virtual_camera import VirtualCameraError

W, H = 320, 180
POSE = ((60, 60, 0, 0, 0), (60, 60, 0, 0, 0))


def wait_until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class FakeCamera:
    def __init__(self, index, w, h, fps, available=True):
        self.frames, self.available, self.status = LatestFrame(), available, "ferma"
        self.frame = np.full((h, w, 3), 90, np.uint8)
        self._stop = threading.Event()
        self.stopped = False

    def start(self):
        self.status = "connessa" if self.available else "webcam non disponibile, nuovo tentativo..."

        def run():
            while not self._stop.wait(0.01):
                if self.available:
                    self.frames.put(self.frame)
        self.t = threading.Thread(target=run, daemon=True)
        self.t.start()

    def stop(self):
        self._stop.set()
        self.t.join()
        self.stopped = True


class FakeVcam:
    instances = []

    def __init__(self, w, h, fps, backend, fail=None):
        self.sent, self.closed, self.fail, self.device = [], False, fail, "Fake Virtual Camera"
        FakeVcam.instances.append(self)

    def open(self):
        if self.fail:
            raise VirtualCameraError(self.fail)

    def send(self, frame):
        self.sent.append(frame.copy())

    def close(self):
        self.closed = True


class FakeDetector:
    def __init__(self, path, hands=None):
        self.hands = hands if hands is not None else []
        self.closed = False

    def detect(self, frame, ts):
        return self.hands

    def close(self):
        self.closed = True


def missing_model(path):
    raise ModelMissingError(f"Modello MediaPipe non trovato: {path}")


def make(detector=missing_model, camera=FakeCamera, vcam=FakeVcam, **settings):
    s = Settings(width=W, height=H, fps=30, **settings)
    return pl.Pipeline(s, camera_factory=camera, vcam_factory=vcam, detector_factory=detector)


def profile_for(pose):
    descs = [descriptor(dedupe_hands(to_aspect(seal(*pose, noise=0.001, rng=np.random.default_rng(i)), W / H)))
             for i in range(20)]
    return GestureProfile.build(descs)


def test_missing_model_still_runs_and_f9_works():
    p = make()
    p.start(True)
    try:
        assert p.recognition_error and "non trovato" in p.recognition_error
        assert p.events.get(timeout=1)[0] == "warning"
        vc = FakeVcam.instances[-1]
        assert wait_until(lambda: len(vc.sent) > 5)
        p.trigger_manual()
        assert wait_until(lambda: p.engine.phase is Phase.SUBSTITUTION)
        assert wait_until(lambda: p.engine.phase is Phase.COOLDOWN, 6)
    finally:
        p.stop()


def test_gesture_triggers_jutsu_automatically():
    det = functools.partial(FakeDetector, hands=seal(*POSE))
    p = make(detector=det, hold_ms=100)
    p.profile = profile_for(POSE)
    p.start(False)
    try:
        assert wait_until(lambda: p.engine.phase is not Phase.IDLE)
        assert p.confidence > 0.9
    finally:
        p.stop()


def test_other_gesture_does_not_trigger():
    det = functools.partial(FakeDetector, hands=seal((0, 0, 0, 0, 0), (0, 0, 0, 0, 0)))
    p = make(detector=det, hold_ms=100)
    p.profile = profile_for(POSE)
    p.start(False)
    try:
        time.sleep(0.6)
        assert p.engine.phase is Phase.IDLE and p.confidence < p.settings.threshold
    finally:
        p.stop()


def test_debug_landmarks_only_in_local_preview():
    det = functools.partial(FakeDetector, hands=seal(*POSE))
    p = make(detector=det, debug=True, recognition_enabled=False)
    p.start(True)
    try:
        vc = FakeVcam.instances[-1]
        assert wait_until(lambda: len(vc.sent) > 10)
        cam_frame = p.camera.frame
        live = [f for f in vc.sent if f.mean() > 60]                    # skip start-up placeholder
        assert len(live) >= 8 and all(np.array_equal(f, cam_frame) for f in live)  # Teams sees the clean frame
        _, preview, _ = p.preview.peek()
        assert not np.array_equal(preview, cam_frame)                   # preview has the overlay
    finally:
        p.stop()


def test_stop_during_animation_releases_everything():
    det = functools.partial(FakeDetector)
    p = make(detector=det)
    p.start(True)
    vc, cam = FakeVcam.instances[-1], p.camera
    detector = p.detector
    p.trigger_manual()
    assert wait_until(lambda: p.engine.phase is Phase.SUBSTITUTION)
    threads = list(p._threads)
    p.stop()
    assert not any(t.is_alive() for t in threads)
    assert vc.closed and cam.stopped and detector.closed
    assert p.engine.phase is Phase.IDLE and not p.running


def test_virtual_camera_failure_starts_nothing():
    p = make(vcam=functools.partial(FakeVcam, fail="Webcam virtuale non trovata"))
    with pytest.raises(VirtualCameraError):
        p.start(True)
    assert p.camera is None and not p.running


def test_camera_unavailable_sends_placeholder_to_keep_teams_feed():
    p = make(camera=functools.partial(FakeCamera, available=False))
    p.start(True)
    try:
        vc = FakeVcam.instances[-1]
        assert wait_until(lambda: len(vc.sent) > 3)
        assert vc.sent[-1].shape == (H, W, 3) and vc.sent[-1].max() > 100   # text on dark frame
        p.camera.available = True
        assert wait_until(lambda: np.array_equal(vc.sent[-1], p.camera.frame))  # reconnection -> live again
    finally:
        p.stop()


def test_gesture_recording_through_pipeline(monkeypatch, isolated_home):
    monkeypatch.setattr(pl, "GestureCalibrator", functools.partial(pl.GestureCalibrator, countdown_s=0.1, record_s=0.5))
    det = functools.partial(FakeDetector, hands=seal(*POSE))
    p = make(detector=det)
    p.start(False)
    try:
        assert p.start_gesture_recording()
        level, text = p.events.get(timeout=3)
        assert level == "info" and "registrato" in text
        assert (isolated_home / pl.SEAL_IMAGE).exists() and p.seal_image is not None
        assert (isolated_home / pl.PROFILE_FILE).exists() and p.profile.confidence(
            descriptor(dedupe_hands(to_aspect(seal(*POSE), W / H)))) > 0.9
    finally:
        p.stop()
