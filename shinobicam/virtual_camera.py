"""Output to the virtual webcam through pyvirtualcam (OBS Virtual Camera or Unity Capture)."""
from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

HINT_NOT_INSTALLED = (
    "Webcam virtuale non trovata.\n"
    "Installa OBS Studio (30 o successivo) da https://obsproject.com, avvialo una volta, "
    "premi 'Avvia videocamera virtuale' e poi 'Ferma videocamera virtuale', chiudi OBS e riprova."
)
HINT_BUSY = (
    "La webcam virtuale e' gia' in uso.\n"
    "Chiudi OBS Studio (o ferma la sua 'Videocamera virtuale') e qualsiasi altra istanza di ShinobiCam, poi riprova."
)


class VirtualCameraError(RuntimeError):
    pass


def explain(err: Exception) -> str:
    msg = str(err)
    low = msg.lower()
    if "not found" in low or "not registered" in low or "did you install" in low or "no camera registered" in low:
        return f"{HINT_NOT_INSTALLED}\n\nDettaglio: {msg}"
    if "could not be started" in low or "in use" in low:
        return f"{HINT_BUSY}\n\nDettaglio: {msg}"
    return f"Impossibile avviare la webcam virtuale: {msg}"


class VirtualCamera:
    def __init__(self, width: int, height: int, fps: int, backend: str = "obs"):
        self.width, self.height, self.fps, self.backend = width, height, fps, backend
        self._cam = None

    @property
    def is_open(self) -> bool:
        return self._cam is not None

    @property
    def device(self) -> str:
        return self._cam.device if self._cam else ""

    def open(self) -> None:
        try:
            import pyvirtualcam
        except ImportError as e:
            raise VirtualCameraError(f"Modulo pyvirtualcam non disponibile: {e}") from e
        try:
            self._cam = pyvirtualcam.Camera(self.width, self.height, self.fps,
                                            fmt=pyvirtualcam.PixelFormat.BGR, backend=self.backend)
        except Exception as e:
            raise VirtualCameraError(explain(e)) from e
        log.info("webcam virtuale aperta: %s (%s)", self._cam.device, self.backend)

    def send(self, frame_bgr: np.ndarray) -> None:
        self._cam.send(frame_bgr)

    def close(self) -> None:
        cam, self._cam = self._cam, None
        if cam is not None:
            try:
                cam.close()
            except Exception:
                log.exception("chiusura webcam virtuale")
