"""System-wide F9 on Windows (works while Teams has focus) via RegisterHotKey."""
from __future__ import annotations

import logging
import sys
import threading
from typing import Callable

log = logging.getLogger(__name__)

WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
VK_F9 = 0x78
MOD_NOREPEAT = 0x4000


class GlobalHotkey:
    """Starts only on Windows; `ok` is False elsewhere or if another app already owns the key."""

    def __init__(self, callback: Callable[[], None], vk: int = VK_F9):
        self.callback, self.vk = callback, vk
        self.ok = False
        self._tid = None
        if sys.platform != "win32":
            return
        ready = threading.Event()
        threading.Thread(target=self._run, args=(ready,), name="hotkey", daemon=True).start()
        ready.wait(2)

    def _run(self, ready: threading.Event) -> None:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._tid = kernel32.GetCurrentThreadId()
        self.ok = bool(user32.RegisterHotKey(None, 1, MOD_NOREPEAT, self.vk))
        ready.set()
        if not self.ok:
            log.warning("F9 globale non registrabile (gia' usato da un'altra app)")
            return
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:
                        log.exception("callback hotkey")
        finally:
            user32.UnregisterHotKey(None, 1)

    def close(self) -> None:
        if self._tid is not None and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
