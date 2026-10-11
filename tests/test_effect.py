import numpy as np
import pytest

from shinobicam.background_manager import BackgroundManager
from shinobicam.effect_engine import (EffectEngine, Phase, Timing, anchor_for, load_log_sprite, make_log_sprite,
                                      overlay_rgba)
from shinobicam.simulate import synthetic_scene
from shinobicam.smoke_renderer import SmokeRenderer

SHAPE = (720, 1280, 3)


def engine():
    return EffectEngine(make_log_sprite(200), Timing(0.5, 2.0, 0.5, 4.0), SmokeRenderer(np.random.default_rng(0)))


def test_state_machine_full_cycle():
    e = engine()
    assert e.trigger(10.0, anchor_for(SHAPE))
    seq = {t: e.update(10.0 + t) for t in (0.1, 0.49, 0.5, 2.4, 2.5, 2.99, 3.0, 6.99, 7.0)}
    assert seq == {0.1: Phase.SMOKE_IN, 0.49: Phase.SMOKE_IN, 0.5: Phase.SUBSTITUTION, 2.4: Phase.SUBSTITUTION,
                   2.5: Phase.SMOKE_OUT, 2.99: Phase.SMOKE_OUT, 3.0: Phase.COOLDOWN, 6.99: Phase.COOLDOWN,
                   7.0: Phase.IDLE}


@pytest.mark.parametrize("t", [0.2, 1.0, 2.7, 5.0])
def test_no_double_activation_during_animation_or_cooldown(t):
    e = engine()
    e.trigger(0.0, anchor_for(SHAPE))
    assert not e.trigger(t, anchor_for(SHAPE))
    assert e.trigger(7.1, anchor_for(SHAPE))


def test_reset_stops_animation():
    e = engine()
    e.trigger(0.0, anchor_for(SHAPE))
    e.reset()
    assert e.phase is Phase.IDLE and not e.smoke.active(0.3)
    frame = np.full(SHAPE, 77, np.uint8)
    assert np.array_equal(e.render(frame, 0.3), frame)


def test_smoke_fully_opaque_inside_cloud_at_peak():
    s = SmokeRenderer(np.random.default_rng(3))
    s.burst((640, 400), (300, 330), 0.0, 0.5, 0.9)
    a = s.alpha_map(SHAPE, 0.5)
    ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    inside = ((xs * 4 - 640) / 300) ** 2 + ((ys * 4 - 400) / 330) ** 2 <= 0.95
    assert a[inside].min() > 0.99
    assert s.alpha_map(SHAPE, 0.05).mean() < a.mean()          # grows in
    assert not s.active(5.0) and s.alpha_map(SHAPE, 5.0) is None  # fades out


def test_composite_with_plate_removes_person():
    bg, person = synthetic_scene()
    bm = BackgroundManager.__new__(BackgroundManager)
    bm.plate = bg
    box = bm.person_bbox(person)
    assert box is not None
    x, y, w, h = box
    assert 0.3 * 1280 < x + w / 2 < 0.7 * 1280 and h > 0.5 * 720
    e = engine()
    e.trigger(0.0, anchor_for(SHAPE, box))
    out = e.render(person, 2.0, bg)                     # mid-substitution, smoke gone
    assert e.phase is Phase.SUBSTITUTION and not e.simplified
    head = (slice(200, 240), slice(600, 680))           # head area: above the log -> background visible
    assert np.abs(out[head].astype(int) - bg[head]).mean() < 3
    assert np.abs(out[head].astype(int) - person[head]).mean() > 20
    log_px = (int(e._anchor.log_center[1]), int(e._anchor.log_center[0]))
    assert np.abs(out[log_px].astype(int) - bg[log_px]).sum() > 30   # log drawn where the torso was
    back = e.render(person, 4.5, bg)                    # cooldown, smoke gone: live video back
    assert np.abs(back.astype(int) - person).mean() < 2


def test_simplified_mode_without_plate_keeps_live_video():
    bg, person = synthetic_scene()
    e = engine()
    e.trigger(0.0, anchor_for(SHAPE, hands_center=(640, 450)))
    out = e.render(person, 2.0, None)
    assert e.simplified
    head = (slice(200, 240), slice(600, 680))
    assert np.abs(out[head].astype(int) - person[head]).mean() < 3


def test_overlay_clips_at_frame_borders():
    dst = np.zeros((100, 100, 3), np.uint8)
    src = np.full((50, 50, 4), 255, np.uint8)
    for cx, cy in [(0, 0), (100, 100), (-30, 50), (500, 500)]:
        overlay_rgba(dst, src, cx, cy)
    assert dst[0, 0].max() == 255 and dst[99, 99].max() == 255 and dst[50, 50].max() == 0


def test_background_capture_flow(tmp_path):
    bm = BackgroundManager(tmp_path / "bg.png")
    assert bm.plate is None
    bm.start_capture(0.0)
    assert bm.feed(np.full(SHAPE, 50, np.uint8), 1.0) is None          # countdown: ignored
    assert "Esci" in bm.message(1.0)
    results = [bm.feed(np.full(SHAPE, 100 + (i % 2) * 10, np.uint8), 5.0 + i * 0.2) for i in range(10)]
    assert results.count("done") == 1 and abs(int(bm.plate[0, 0, 0]) - 105) <= 1
    assert BackgroundManager(tmp_path / "bg.png").plate is not None   # persisted
    assert bm.plate_for((360, 640, 3)) is None                          # resolution changed -> recalibrate
    bm.clear()
    assert bm.plate is None and not (tmp_path / "bg.png").exists()


def test_custom_log_png_and_fallbacks(tmp_path):
    import cv2
    p = tmp_path / "custom_tronco.png"
    cv2.imwrite(str(p), np.full((40, 20, 3), 9, np.uint8))
    sprite, src = load_log_sprite(str(p))
    assert sprite.shape == (40, 20, 4) and src == str(p)
    sprite, src = load_log_sprite(str(tmp_path / "missing.png"))
    assert sprite.shape[2] == 4 and src.endswith("log.png")
