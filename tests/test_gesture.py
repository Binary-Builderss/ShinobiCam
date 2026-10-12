import numpy as np
import pytest

from handgen import seal
from shinobicam.config import MODEL_RELPATH, resource_path
from shinobicam.gesture_calibration import GestureCalibrator
from shinobicam.gesture_detector import (GestureProfile, GestureTrigger, HandDetector, ModelMissingError,
                                         dedupe_hands, descriptor, distance, to_aspect)

ASPECT = 16 / 9
TIGER = ((60, 60, 0, 0, 0), (60, 60, 0, 0, 0))       # index+middle up, others curled... roughly
RAM = ((10, 90, 90, 0, 0), (10, 90, 90, 0, 0))
OPEN = ((0, 0, 0, 0, 0), (0, 0, 0, 0, 0))
FIST = ((90, 100, 100, 100, 100), (90, 100, 100, 100, 100))


def desc(hands):
    return descriptor(dedupe_hands(to_aspect(hands, ASPECT)))


def record(pose, n=40, rng=None, **kw):
    rng = rng or np.random.default_rng(1)
    return [desc(seal(*pose, cx=0.5 + rng.uniform(-.05, .05), cy=0.6 + rng.uniform(-.05, .05),
                      scale=0.15 * rng.uniform(.9, 1.1), angle=rng.uniform(-8, 8), noise=0.0015, rng=rng, **kw))
            for _ in range(n)]


def test_descriptor_invariant_to_position_scale_rotation_and_hand_order():
    base = desc(seal(*TIGER))
    moved = desc(seal(*TIGER, cx=0.3, cy=0.4, scale=0.22, angle=35))
    reordered = desc(list(reversed(seal(*TIGER, cx=0.3, cy=0.4, scale=0.22, angle=35))))
    assert distance(base, moved) < 1e-6
    assert distance(moved, reordered) < 1e-6
    assert distance(base, desc(seal(*RAM))) > 0.2


def test_profile_matches_own_seal_and_rejects_others():
    profile = GestureProfile.build(record(TIGER), "Tigre")
    test = record(TIGER, n=20, rng=np.random.default_rng(7))
    assert np.mean([profile.confidence(d) for d in test]) > 0.8
    for other in (RAM, OPEN, FIST):
        assert max(profile.confidence(d) for d in record(other, n=20)) < 0.3, other


def test_overlapping_hands_single_hand_samples():
    """Seal recorded while MediaPipe sometimes sees only one hand: both variants must match."""
    two = record(TIGER, n=20)
    one = [desc(seal(*TIGER)[:1]) for _ in range(10)]
    profile = GestureProfile.build(two + one)
    assert set(profile.samples) == {1, 2}
    assert profile.confidence(desc(seal(*TIGER)[:1])) > 0.9
    assert profile.confidence(None) == 0.0


def test_duplicate_detection_of_same_hand_is_merged():
    h = seal(*TIGER)[0]
    assert len(dedupe_hands([h, h + 0.001])) == 1
    assert len(dedupe_hands(seal(*TIGER))) == 2


def test_profile_needs_enough_samples():
    with pytest.raises(ValueError, match="campioni"):
        GestureProfile.build(record(TIGER, n=3))


def test_profile_save_load_and_corrupt_file(tmp_path):
    p = tmp_path / "g.json"
    prof = GestureProfile.build(record(TIGER))
    prof.save(p)
    loaded = GestureProfile.load(p)
    d = desc(seal(*TIGER))
    assert abs(loaded.confidence(d) - prof.confidence(d)) < 1e-3
    p.write_text('{"name": "x", "tolerance": 0.2, "samples": {"2": [[1, 2]]}}')
    assert GestureProfile.load(p) is None
    assert GestureProfile.load(tmp_path / "missing.json") is None


def test_trigger_requires_hold_and_tolerates_short_dropout():
    t = GestureTrigger(hold_s=0.3, grace_s=0.2)
    assert not t.update(True, 0.0)
    assert not t.update(True, 0.2)
    assert not t.update(False, 0.25)     # brief miss within grace
    assert t.update(True, 0.31)          # held 0.31 s -> fire
    assert not t.update(True, 0.5)       # no re-fire while still held
    t.update(False, 0.6)
    t.update(False, 0.9)                 # released past grace -> re-armed
    assert not t.update(True, 1.0)
    assert t.update(True, 1.35)


def test_trigger_flicker_does_not_fire():
    t = GestureTrigger(hold_s=0.3, grace_s=0.05)
    fired = [t.update(i % 4 == 0, i * 0.033) for i in range(60)]
    assert not any(fired)


def test_calibrator_flow():
    cal = GestureCalibrator(now=0.0, countdown_s=1.0, record_s=1.0)
    cal.feed(seal(*TIGER), ASPECT, 0.5)   # countdown: ignored
    assert "Prepara" in cal.message(0.5)
    for i in range(30):
        cal.feed(seal(*TIGER), ASPECT, 1.0 + i / 30)
    cal.feed([], ASPECT, 1.5)             # no hands: counted as frame, no sample
    assert cal.done(2.0) and len(cal.descriptors) == 30
    assert not cal.hands_lost(1.99)
    assert cal.result().confidence(desc(seal(*TIGER))) > 0.9


def test_missing_model_raises(tmp_path):
    with pytest.raises(ModelMissingError):
        HandDetector(tmp_path / "nope.task")


@pytest.mark.skipif(not resource_path(MODEL_RELPATH).is_file(), reason="modello non scaricato")
def test_real_model_runs_on_empty_frame():
    det = HandDetector(resource_path(MODEL_RELPATH))
    try:
        assert det.detect(np.zeros((720, 1280, 3), np.uint8), 0) == []
        assert det.detect(np.zeros((720, 1280, 3), np.uint8), 0) == []  # same ts: auto-incremented
    finally:
        det.close()


def test_calibrator_warns_live_when_hands_leave():
    cal = GestureCalibrator(now=0.0, countdown_s=1.0, record_s=2.0)
    assert not cal.hands_lost(0.5) and not cal.hands_lost(1.3)    # countdown, then grace at start
    frame = np.zeros((10, 10, 3), np.uint8)
    cal.feed(seal(*TIGER), ASPECT, 1.4, frame)
    cal.feed([], ASPECT, 2.0)
    assert cal.hands_lost(2.0) and "Non vedo le mani" in cal.message(2.0)
    assert cal.snapshot is not None and cal.snapshot[0] is frame
