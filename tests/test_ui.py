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
        monkeypatch.setattr(ui.messagebox, name, lambda *a, _n=name, **k: shown.append((_n, a)))
    monkeypatch.setattr(ui.messagebox, "askokcancel", lambda *a, **k: shown.append(("ask", a)) or False)
    monkeypatch.setattr(ui, "obs_running", lambda: False)
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


def test_guided_flow_start_steps_and_stop(app):
    assert app.cam_box["values"][1].endswith("(virtuale)")
    assert app.cam_var.get() == "Integrated Webcam"          # physical camera preselected
    assert app.onair.cget("text").endswith("SPENTO")
    app.record_seal()                                         # not running yet -> hint, no crash
    assert "Avvia prima" in app.toast_text
    assert str(app.step_bg.button.cget("state")) == "disabled"

    app.open_settings()
    app.res_var.set("640x360")
    app.start(True)
    pump(app, 0.6)
    assert app.pipeline.running and app._photo is not None
    assert "IN ONDA" in app.onair.cget("text") and "Fake Virtual Camera" in app.onair.cget("text")
    assert app.step_start.badge.cget("text") == "✓"
    assert app.btn_main.cget("text").endswith("Arresta")
    assert str(app.video_boxes[0].cget("state")) == "disabled"  # resolution locked while running

    app.calibrate_bg()
    pump(app, 0.3)
    assert app.step_bg.badge.cget("text") == "…"
    app.record_seal()
    pump(app, 0.3)
    assert app.step_seal.badge.cget("text") == "…"
    app.test_jutsu()
    app.restore_normal()
    assert app.settings.recognition_enabled is False and "Webcam normale" in app.toast_text
    app.stop()
    assert not app.pipeline.running and app.btn_main.cget("text").endswith("Avvia webcam virtuale")
    assert not [s for s in app.shown if s[0] == "showerror"], app.shown


def test_preview_only_mode_badge(app):
    app.start(False)
    pump(app, 0.3)
    assert "SOLO ANTEPRIMA" in app.onair.cget("text")


def test_pipeline_events_become_toasts_not_popups(app):
    app.pipeline.events.put(("info", "Sfondo acquisito."))
    app._refresh_status()
    assert app.toast_text == "Sfondo acquisito." and not app.shown
    app.hide_toast()
    assert app.toast_text == ""


def test_refuses_virtual_camera_as_source(app):
    app.cam_var.set(app.cam_box["values"][1])
    app.start(True)
    assert not app.pipeline.running
    assert app.shown and "virtuale" in app.shown[-1][1][1]


def test_reports_missing_backend(app):
    app.pipeline._vcam_factory = functools.partial(FakeVcam, fail="Webcam virtuale non trovata. Installa OBS")
    app.start(True)
    assert not app.pipeline.running
    assert app.shown[-1][0] == "showerror" and "OBS" in app.shown[-1][1][1]


def test_warns_when_obs_is_open(app, monkeypatch):
    monkeypatch.setattr(ui, "obs_running", lambda: True)
    app.start(True)                     # askokcancel patched to "Annulla"
    assert app.shown[-1][0] == "ask" and not app.pipeline.running
