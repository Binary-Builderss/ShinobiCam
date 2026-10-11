import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep tests away from the real %APPDATA%\\ShinobiCam."""
    monkeypatch.setenv("SHINOBICAM_HOME", str(tmp_path / "home"))
    return tmp_path / "home"
