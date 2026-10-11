import sys
from pathlib import Path

import cv2
import pytest

from shinobicam import config
from shinobicam.config import LOG_SPRITE_RELPATH, MODEL_RELPATH, resource_path

ROOT = Path(__file__).resolve().parent.parent


def test_bundled_assets_present_and_valid():
    sprite = cv2.imread(str(resource_path(LOG_SPRITE_RELPATH)), cv2.IMREAD_UNCHANGED)
    assert sprite is not None and sprite.shape[2] == 4 and sprite[..., 3].min() == 0 and sprite[..., 3].max() == 255
    assert resource_path("assets/icon.ico").stat().st_size > 1000


def test_resource_path_inside_pyinstaller_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_path(MODEL_RELPATH) == tmp_path / "models" / "hand_landmarker.task"


def test_data_dir_uses_appdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("SHINOBICAM_HOME")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert config.data_dir() == tmp_path / "ShinobiCam" and (tmp_path / "ShinobiCam").is_dir()


def test_spec_bundles_model_assets_and_native_libs():
    spec = (ROOT / "ShinobiCam.spec").read_text()
    for needle in ('"models/hand_landmarker.task", "models"', '"assets/log.png", "assets"',
                   '"assets/icon.ico", "assets"', 'collect_dynamic_libs("mediapipe")', '"mediapipe.tasks.c"'):
        assert needle in spec


@pytest.mark.skipif(not (ROOT / "dist" / "ShinobiCam").is_dir(), reason="build non presente")
def test_built_bundle_contains_resources():
    internal = ROOT / "dist" / "ShinobiCam" / "_internal"
    assert (internal / "models" / "hand_landmarker.task").is_file()
    assert (internal / "assets" / "log.png").is_file()
    assert list((internal / "mediapipe" / "tasks" / "c").glob("libmediapipe.*"))
