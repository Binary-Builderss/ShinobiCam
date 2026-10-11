import sys
import threading
import time
import types

import numpy as np
import pytest

from shinobicam.camera_manager import CameraManager, LatestFrame, fit_frame, is_virtual
from shinobicam.config import Settings
from shinobicam.virtual_camera import VirtualCamera, VirtualCameraError


def wait_until(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class FakeCap:
    def __init__(self, frames_before_loss=None, shape=(480, 640, 3)):
        self.left = frames_before_loss
        self.shape = shape
        self.released = False

    def read(self):
        if self.left is not None:
            if self.left <= 0:
                return False, None
            self.left -= 1
        return True, np.full(self.shape, 100, np.uint8)

    def release(self):
        self.released = True


def test_latest_frame_drops_stale_items():
    slot = LatestFrame()
    for i in range(5):
        slot.put(i)
    seq, item = slot.get(after_seq=0, timeout=0.1)
    assert (seq, item) == (5, 4)
    assert slot.get(after_seq=seq, timeout=0.05) == (5, None)


def test_fit_frame_crops_to_aspect():
    f = np.zeros((480, 640, 3), np.uint8)
    f[:, 300:340] = 255
    out = fit_frame(f, 1280, 720)
    assert out.shape == (720, 1280, 3)
    assert out[360, 640].max() == 255  # center stays centered, no stretch


def test_camera_unavailable_keeps_retrying_without_crash():
    calls = []
    cam = CameraManager(0, 640, 360, 30, opener=lambda *a: calls.append(a) or None)
    cam.RETRY_S = 0.01
    cam.start()
    assert wait_until(lambda: len(calls) >= 3)
    assert not cam.connected and "non disponibile" in cam.status
    cam.stop()
    assert not cam._thread.is_alive()


def test_camera_reconnects_after_loss():
    caps = [FakeCap(frames_before_loss=3), FakeCap()]
    cam = CameraManager(0, 640, 360, 30, opener=lambda *a: caps.pop(0) if caps else None)
    cam.MAX_FAILED_READS = 2
    cam.start()
    assert wait_until(lambda: not caps and cam.connected and cam.frames.peek()[0] > 10)
    seq, frame, _ = cam.frames.peek()
    assert frame.shape == (360, 640, 3)
    cam.stop()


def test_virtual_camera_names_flagged():
    assert is_virtual("OBS Virtual Camera")
    assert not is_virtual("Integrated Webcam")


def _fake_pyvirtualcam(monkeypatch, exc):
    mod = types.SimpleNamespace(PixelFormat=types.SimpleNamespace(BGR="bgr"))
    def camera(*a, **k):
        raise exc
    mod.Camera = camera
    monkeypatch.setitem(sys.modules, "pyvirtualcam", mod)


def test_backend_not_installed_gives_italian_hint(monkeypatch):
    _fake_pyvirtualcam(monkeypatch, RuntimeError("OBS Virtual Camera device not found! Did you install OBS?"))
    with pytest.raises(VirtualCameraError, match="Installa OBS"):
        VirtualCamera(1280, 720, 30).open()


def test_backend_busy_gives_italian_hint(monkeypatch):
    _fake_pyvirtualcam(monkeypatch, RuntimeError("virtual camera output could not be started"))
    with pytest.raises(VirtualCameraError, match="gia' in uso"):
        VirtualCamera(1280, 720, 30).open()


def test_pyvirtualcam_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyvirtualcam", None)
    with pytest.raises(VirtualCameraError, match="pyvirtualcam"):
        VirtualCamera(1280, 720, 30).open()


def test_settings_roundtrip_and_bad_values(isolated_home):
    s = Settings(threshold=0.8, camera_index=2)
    s.save()
    assert Settings.load().threshold == 0.8
    p = isolated_home / "settings.json"
    p.write_text('{"threshold": "high", "fps": 24, "backend": "evil", "cooldown_s": 3}')
    s = Settings.load()
    assert (s.threshold, s.fps, s.backend, s.cooldown_s) == (0.6, 24, "obs", 3.0)
    p.write_text("{broken")
    assert Settings.load() == Settings()


def test_mac_camera_names_follow_opencv_uniqueid_order():
    from shinobicam.camera_manager import mac_camera_names
    js = ('{"SPCameraDataType": ['
          '{"_name": "OBS Virtual Camera", "spcamera_unique-id": "7626645E"},'
          '{"_name": "FaceTime HD Camera", "spcamera_unique-id": "47B4B64B"},'
          '{"_name": "iPhone Camera", "spcamera_unique-id": "CA47AC04"}]}')
    assert mac_camera_names(js) == ["FaceTime HD Camera", "OBS Virtual Camera", "iPhone Camera"]
