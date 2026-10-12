import functools
import time
import tkinter as tk

import numpy as np
import pytest

import shinobicam.ui as ui
from handgen import seal
from test_pipeline import POSE, FakeCamera, FakeDetector, FakeVcam


def make_app(monkeypatch):
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
    return a


@pytest.fixture
def app(monkeypatch):
    a = make_app(monkeypatch)
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
    assert "virtuale" in app.toast_text and not app.shown


def test_reports_missing_backend(app):
    app.pipeline._vcam_factory = functools.partial(FakeVcam, fail="Webcam virtuale non trovata. Installa OBS")
    app.start(True)
    assert not app.pipeline.running
    assert "OBS" in app.toast_text and not app.shown
    assert app.preview.cget("text") == "Anteprima spenta"   # loading text cleared on failure


def test_warns_when_obs_is_open(app, monkeypatch):
    monkeypatch.setattr(ui, "obs_running", lambda: True)
    app.start(True)                     # askokcancel patched to "Annulla"
    assert app.shown[-1][0] == "ask" and not app.pipeline.running


def test_settings_window_rows_do_not_overlap(app):
    app.open_settings()
    body = app.settings_win.winfo_children()[0]
    rows: dict[int, list[tuple[int, int]]] = {}
    for w in body.grid_slaves():
        gi = w.grid_info()
        rows.setdefault(int(gi["row"]), []).append((int(gi["column"]), int(gi["columnspan"])))
    for r, cells in rows.items():
        used = [c for col, span in cells for c in range(col, col + span)]
        assert len(used) == len(set(used)), f"riga {r}: {cells}"


def test_compact_mode_mirrors_state(app):
    app.start(True)
    pump(app, 0.4)
    app.enter_compact()
    assert app.compact and "IN ONDA" in app.mini_onair.cget("text")
    app.show_toast("warning", "webcam persa")
    assert app.mini_msg.cget("text") == "webcam persa"
    app.exit_compact()
    assert not app.compact


def test_keyboard_shortcuts(app):
    app.root.update()
    app.root.focus_force()
    app.root.update()
    if app.root.focus_get() is None:
        pytest.skip("la finestra di test non riceve il focus")
    app.root.event_generate("<space>", when="tail")
    app.root.update()
    assert "Avvia prima" in app.toast_text            # Space = Testa sostituzione
    app.root.event_generate("<Escape>", when="tail")
    app.root.update()
    assert "Webcam normale" in app.toast_text         # Esc = Webcam normale


def test_thumbnails_for_background_and_seal(app):
    assert not app.step_bg.thumb.winfo_manager()
    app.pipeline.background.plate = np.zeros((720, 1280, 3), np.uint8)
    app._refresh_status()
    assert app.step_bg.thumb.winfo_manager() == "grid"


def test_autostart(monkeypatch):
    ui.Settings(autostart=True).save()
    a = make_app(monkeypatch)
    try:
        pump(a, 1.0)
        assert a.pipeline.running and "IN ONDA" in a.onair.cget("text")
    finally:
        a.on_close()
