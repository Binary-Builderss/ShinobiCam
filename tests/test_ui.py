import functools
import time
import tkinter as tk

import pytest

import shinobicam.ui as ui
from handgen import seal
from test_pipeline import POSE, FakeCamera, FakeDetector, FakeVcam


@pytest.fixture
def app(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("nessun display")
    shown = []
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(ui.messagebox, name, lambda *a, _n=name: shown.append((_n, a)))
    monkeypatch.setattr(ui.messagebox, "askokcancel", lambda *a: True)
    monkeypatch.setattr(ui, "list_cameras", lambda: [(0, "Integrated Webcam"), (1, "OBS Virtual Camera")])
    a = ui.App(root)
    p = a.pipeline
    p._camera_factory = FakeCamera
    p._vcam_factory = FakeVcam
    p._detector_factory = functools.partial(FakeDetector, hands=seal(*POSE))
    a.shown = shown
    yield a
    a.on_close()


def pump(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.root.update()
        time.sleep(0.01)


def test_ui_start_preview_controls_and_close(app):
    assert app.cam_box["values"][1].endswith("(virtuale - non usare)")
    app.res_var.set("640x360")
    app.start(True)
    pump(app, 0.6)
    assert app.pipeline.running and app._photo is not None
    assert "Fake Virtual Camera" in app.vcam_label.cget("text")
    app.pipeline.trigger_manual()
    app.calibrate_bg()
    app.record_seal()
    app.restore_normal()
    assert app.settings.recognition_enabled is False
    pump(app, 0.3)
    app.stop()
    assert not app.pipeline.running
    assert not [s for s in app.shown if s[0] == "showerror"], app.shown


def test_ui_refuses_virtual_camera_as_source(app):
    app.cam_var.set(app.cam_box["values"][1])
    app.start(True)
    assert not app.pipeline.running
    assert app.shown and "virtuale" in app.shown[-1][1][1]


def test_ui_reports_missing_backend(app):
    app.pipeline._vcam_factory = functools.partial(FakeVcam, fail="Webcam virtuale non trovata. Installa OBS")
    app.start(True)
    assert not app.pipeline.running
    assert app.shown[-1][0] == "showerror" and "OBS" in app.shown[-1][1][1]
