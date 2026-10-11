"""Entry point: GUI by default, `--selftest` to check a build, `--simulate OUT.mp4` for an offline demo."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
import threading

from . import __version__
from .config import LOG_SPRITE_RELPATH, MODEL_RELPATH, data_dir, resource_path

log = logging.getLogger("shinobicam")


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.handlers.RotatingFileHandler(
        data_dir() / "shinobicam.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if sys.stderr is not None:  # windowed EXE has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s",
                        handlers=handlers)
    sys.excepthook = lambda *exc: log.critical("eccezione non gestita", exc_info=exc)
    threading.excepthook = lambda a: log.critical("eccezione nel thread %s", a.thread and a.thread.name,
                                                  exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def selftest() -> int:
    """Checks bundled resources and native libs. Exit 0 if the app can run; the virtual camera is reported only."""
    import numpy as np
    lines, ok = [f"ShinobiCam {__version__} selftest"], True

    def check(name, fn, required=True):
        nonlocal ok
        try:
            lines.append(f"[OK]   {name}: {fn()}")
        except Exception as e:
            lines.append(f"[{'FAIL' if required else 'WARN'}] {name}: {e}")
            ok = ok and not required

    def model():
        from .gesture_detector import HandDetector
        det = HandDetector(resource_path(MODEL_RELPATH))
        try:
            return f"{len(det.detect(np.zeros((360, 640, 3), np.uint8), 0))} mani su frame vuoto"
        finally:
            det.close()

    def sprite():
        from .effect_engine import load_log_sprite
        img, src = load_log_sprite()
        if not src.endswith("log.png"):
            raise RuntimeError(f"asset {LOG_SPRITE_RELPATH} mancante (fallback {src})")
        return f"{img.shape} da {src}"

    def vcam():
        from .virtual_camera import VirtualCamera
        cam = VirtualCamera(640, 360, 30)
        cam.open()
        try:
            return cam.device
        finally:
            cam.close()

    def cameras():
        from .camera_manager import list_cameras
        return list_cameras() or "nessuna"

    check("modello MediaPipe", model)
    check("asset tronco", sprite)
    check("icona", lambda: resource_path("assets/icon.ico").stat().st_size)
    check("tkinter", lambda: __import__("tkinter").TkVersion)
    check("webcam virtuale", vcam, required=False)
    check("webcam fisiche", cameras, required=False)
    lines.append("RISULTATO: " + ("OK" if ok else "FALLITO"))
    report = "\n".join(lines)
    (data_dir() / "selftest.txt").write_text(report, encoding="utf-8")
    log.info("\n%s", report)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ShinobiCam")
    ap.add_argument("--selftest", action="store_true", help="verifica modello, asset e backend; esito in selftest.txt")
    ap.add_argument("--simulate", metavar="OUT.mp4", help="genera un video dimostrativo dell'effetto, senza webcam")
    a = ap.parse_args(argv)
    setup_logging()
    if a.selftest:
        return selftest()
    if a.simulate:
        from .simulate import main as simulate_main
        simulate_main([a.simulate])
        return 0
    from .ui import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
