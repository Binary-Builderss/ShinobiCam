"""Tkinter GUI."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from .camera_manager import is_virtual, list_cameras
from .config import BACKENDS, FPS_CHOICES, RESOLUTIONS, Settings, data_dir
from .hotkey import GlobalHotkey
from .pipeline import Pipeline
from .virtual_camera import VirtualCameraError

log = logging.getLogger(__name__)
PREVIEW_W, PREVIEW_H = 640, 360


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings.load()
        self.pipeline = Pipeline(self.settings)
        self.cameras: list[tuple[int, str]] = []
        self._photo = None
        self._preview_seq = 0
        self._ticks = 0

        root.title("ShinobiCam - Kawarimi no Jutsu")
        root.minsize(1000, 560)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.hotkey = GlobalHotkey(self.pipeline.trigger_manual)
        if not self.hotkey.ok:
            root.bind("<F9>", lambda e: self.pipeline.trigger_manual())  # only while this window has focus
        self.refresh_cameras()
        self._sync_running(False)
        self._tick()

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        s = self.settings
        left = ttk.Frame(self.root, padding=10)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(self.root, padding=10)
        right.grid(row=0, column=1, sticky="nsew")
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        cam = ttk.LabelFrame(left, text="Webcam fisica", padding=8)
        cam.pack(fill="x")
        self.cam_var = tk.StringVar()
        self.cam_box = ttk.Combobox(cam, textvariable=self.cam_var, state="readonly", width=34)
        self.cam_box.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.btn_refresh = ttk.Button(cam, text="Aggiorna", command=self.refresh_cameras)
        self.btn_refresh.grid(row=0, column=2, padx=(4, 0))
        ttk.Label(cam, text="Risoluzione").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.res_var = tk.StringVar(value=f"{s.width}x{s.height}")
        self.res_box = ttk.Combobox(cam, textvariable=self.res_var, values=list(RESOLUTIONS), state="readonly", width=10)
        self.res_box.grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(cam, text="FPS").grid(row=2, column=0, sticky="w")
        self.fps_var = tk.StringVar(value=str(s.fps))
        self.fps_box = ttk.Combobox(cam, textvariable=self.fps_var, values=[str(f) for f in FPS_CHOICES],
                                    state="readonly", width=10)
        self.fps_box.grid(row=2, column=1, sticky="w")
        ttk.Label(cam, text="Backend").grid(row=3, column=0, sticky="w")
        self.backend_var = tk.StringVar(value=s.backend)
        self.backend_box = ttk.Combobox(cam, textvariable=self.backend_var, values=list(BACKENDS), state="readonly",
                                        width=12)
        self.backend_box.grid(row=3, column=1, sticky="w")

        vc = ttk.LabelFrame(left, text="Webcam virtuale", padding=8)
        vc.pack(fill="x", pady=(8, 0))
        self.btn_start = ttk.Button(vc, text="Avvia webcam virtuale", command=lambda: self.start(True))
        self.btn_start.grid(row=0, column=0, sticky="ew")
        self.btn_sim = ttk.Button(vc, text="Solo anteprima (simulazione)", command=lambda: self.start(False))
        self.btn_sim.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.btn_stop = ttk.Button(vc, text="Arresta", command=self.stop)
        self.btn_stop.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.vcam_label = tk.Label(vc, text="● Webcam virtuale spenta", fg="#999999", anchor="w")
        self.vcam_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        j = ttk.LabelFrame(left, text="Jutsu", padding=8)
        j.pack(fill="x", pady=(8, 0))
        for i, (text, cmd) in enumerate([("Registra sigillo", self.record_seal), ("Calibra sfondo", self.calibrate_bg),
                                         ("Testa sostituzione (F9)", self.pipeline.trigger_manual),
                                         ("Ripristina webcam normale", self.restore_normal)]):
            ttk.Button(j, text=text, command=cmd).grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        self.recog_var = tk.BooleanVar(value=s.recognition_enabled)
        ttk.Checkbutton(j, text="Riconoscimento sigillo attivo", variable=self.recog_var,
                        command=self._apply_live).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.debug_var = tk.BooleanVar(value=s.debug)
        ttk.Checkbutton(j, text="Debug: landmark mani (solo anteprima locale)", variable=self.debug_var,
                        command=self._apply_live).grid(row=3, column=0, columnspan=2, sticky="w")
        self.thr_var = tk.DoubleVar(value=s.threshold)
        self.cool_var = tk.DoubleVar(value=s.cooldown_s)
        self.sub_var = tk.DoubleVar(value=s.substitution_ms / 1000)
        for r, (label, var, lo, hi) in enumerate([("Soglia confidenza", self.thr_var, 0.3, 0.95),
                                                  ("Cooldown (s)", self.cool_var, 3.0, 5.0),
                                                  ("Durata tronco (s)", self.sub_var, 1.8, 2.5)], start=4):
            ttk.Label(j, text=label).grid(row=r, column=0, sticky="w")
            ttk.Scale(j, from_=lo, to=hi, variable=var, command=lambda _v: self._apply_live()).grid(
                row=r, column=1, sticky="ew")
        self.scale_label = ttk.Label(j, text="")
        self.scale_label.grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Button(j, text="Carica tronco PNG...", command=self.load_sprite).grid(row=8, column=0, sticky="ew", padx=2)
        ttk.Button(j, text="Tronco predefinito", command=lambda: self.set_sprite("")).grid(row=8, column=1,
                                                                                         sticky="ew", padx=2)

        st = ttk.LabelFrame(left, text="Stato", padding=8)
        st.pack(fill="x", pady=(8, 0))
        self.status_label = ttk.Label(st, text="", justify="left", wraplength=330)
        self.status_label.pack(fill="x")
        self.conf_bar = ttk.Progressbar(st, maximum=1.0, length=300)
        self.conf_bar.pack(fill="x", pady=(4, 0))
        self.bg_label = tk.Label(st, text="", justify="left", wraplength=330, anchor="w")
        self.bg_label.pack(fill="x", pady=(4, 0))

        self.preview = tk.Label(right, bg="#1e1e1e", fg="#cccccc", text="Anteprima spenta\n\nSeleziona la webcam e premi Avvia")
        self.preview.pack(fill="both", expand=True)
        self.msg_label = ttk.Label(right, text="", wraplength=700, justify="left")
        self.msg_label.pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------ actions
    def refresh_cameras(self) -> None:
        self.cameras = list_cameras()
        values = [f"{i}: {n}" + ("  (virtuale - non usare)" if is_virtual(n) else "") for i, n in self.cameras]
        self.cam_box["values"] = values
        current = [v for (i, _), v in zip(self.cameras, values) if i == self.settings.camera_index]
        self.cam_var.set(current[0] if current else (values[0] if values else ""))
        if not values:
            self.msg("Nessuna webcam trovata. Collegala e premi Aggiorna.")

    def _apply_live(self) -> None:
        s = self.settings
        s.recognition_enabled = self.recog_var.get()
        s.debug = self.debug_var.get()
        s.threshold = round(self.thr_var.get(), 2)
        s.cooldown_s = round(self.cool_var.get(), 1)
        s.substitution_ms = int(round(self.sub_var.get(), 1) * 1000)
        self.scale_label.config(text=f"soglia {s.threshold:.2f} | cooldown {s.cooldown_s:.1f}s | "
                                     f"tronco {s.substitution_ms / 1000:.1f}s")

    def _apply_start_settings(self) -> bool:
        s = self.settings
        sel = self.cam_var.get()
        if not sel:
            messagebox.showerror("ShinobiCam", "Nessuna webcam selezionata.")
            return False
        index = int(sel.split(":", 1)[0])
        name = dict(self.cameras).get(index, "")
        if is_virtual(name):
            messagebox.showerror("ShinobiCam", "Hai selezionato una webcam virtuale come sorgente.\n"
                                               "Seleziona la webcam fisica (altrimenti l'immagine entra in loop).")
            return False
        s.camera_index = index
        s.width, s.height = RESOLUTIONS[self.res_var.get()]
        s.fps = int(self.fps_var.get())
        s.backend = self.backend_var.get()
        self._apply_live()
        s.save()
        return True

    def start(self, use_vcam: bool) -> None:
        if not self._apply_start_settings():
            return
        try:
            self.pipeline.start(use_virtual_camera=use_vcam)
        except VirtualCameraError as e:
            self.pipeline.stop()
            messagebox.showerror("Webcam virtuale", str(e))
            return
        except Exception as e:
            log.exception("avvio")
            self.pipeline.stop()
            messagebox.showerror("ShinobiCam", f"Avvio fallito: {e}")
            return
        self._sync_running(True)
        if use_vcam:
            self.msg(f"In Teams: Impostazioni > Dispositivi > Fotocamera > '{self.pipeline.vcam.device}'.")
        else:
            self.msg("Modalita' simulazione: l'effetto e' visibile solo qui, nulla viene inviato a Teams.")

    def stop(self) -> None:
        self.pipeline.stop()
        self._sync_running(False)
        self._photo = None
        self.preview.config(image="", text="Anteprima spenta")

    def _sync_running(self, running: bool) -> None:
        for w in (self.cam_box, self.res_box, self.fps_box, self.backend_box):
            w.config(state="disabled" if running else "readonly")
        for w in (self.btn_refresh, self.btn_start, self.btn_sim):
            w.config(state="disabled" if running else "normal")
        self.btn_stop.config(state="normal" if running else "disabled")

    def _require_running(self) -> bool:
        if not self.pipeline.running:
            messagebox.showinfo("ShinobiCam", "Avvia prima la webcam (webcam virtuale o solo anteprima).")
            return False
        return True

    def record_seal(self) -> None:
        if not self._require_running():
            return
        if not self.pipeline.start_gesture_recording():
            messagebox.showerror("ShinobiCam", f"Riconoscimento non disponibile:\n{self.pipeline.recognition_error}")
            return
        self.msg("Tra 3 secondi esegui il sigillo e tienilo per 4 secondi, muovendo leggermente le mani "
                 "(avanti/indietro, poco a destra/sinistra) per renderlo piu' robusto.")

    def calibrate_bg(self) -> None:
        if not self._require_running():
            return
        if messagebox.askokcancel("Calibra sfondo", "Hai 5 secondi per uscire dall'inquadratura.\n"
                                                    "La webcam NON deve muoversi; poi ShinobiCam acquisisce lo sfondo vuoto."):
            self.pipeline.start_background_capture()

    def restore_normal(self) -> None:
        self.pipeline.reset_effect()
        self.recog_var.set(False)
        self._apply_live()
        self.msg("Webcam normale: effetto interrotto e riconoscimento disattivato. Riattivalo dalla casella.")

    def load_sprite(self) -> None:
        path = filedialog.askopenfilename(title="PNG del tronco (con trasparenza)", filetypes=[("PNG", "*.png")])
        if path:
            self.set_sprite(path)

    def set_sprite(self, path: str) -> None:
        src = self.pipeline.set_log_sprite(path)
        if path and src != path:
            messagebox.showwarning("ShinobiCam", "Immagine non valida: uso il tronco predefinito.")
            path = ""
        self.settings.log_image = path
        self.settings.save()
        self.msg(f"Tronco: {src}")

    def msg(self, text: str) -> None:
        self.msg_label.config(text=text)

    # ------------------------------------------------------------ periodic UI refresh
    def _tick(self) -> None:
        try:
            seq, frame, _ = self.pipeline.preview.peek()
            if frame is not None and seq != self._preview_seq and self.pipeline.running:
                self._preview_seq = seq
                w = max(self.preview.winfo_width(), 320)
                h = max(self.preview.winfo_height(), 180)
                fh, fw = frame.shape[:2]
                k = min(w / fw, h / fh)
                small = cv2.resize(frame, (max(int(fw * k), 1), max(int(fh * k), 1)), interpolation=cv2.INTER_AREA)
                self._photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
                self.preview.config(image=self._photo, text="")
            self._ticks += 1
            if self._ticks % 8 == 0:
                self._refresh_status()
        except Exception:
            log.exception("aggiornamento UI")
        self.root.after(30, self._tick)

    def _refresh_status(self) -> None:
        p = self.pipeline
        st = p.status()
        if st["vcam"]:
            self.vcam_label.config(text=f"● Webcam virtuale attiva: {st['vcam']}", fg="#1a9e3a")
        elif p.running:
            self.vcam_label.config(text="● Solo anteprima (nessun invio a Teams)", fg="#d08000")
        else:
            self.vcam_label.config(text="● Webcam virtuale spenta", fg="#999999")
        if st["recognition_error"]:
            recog = "non disponibile (usa F9)"
        elif not self.settings.recognition_enabled:
            recog = "disattivato"
        elif not st["profile"]:
            recog = "nessun sigillo registrato"
        else:
            recog = f"{st['profile']} - conf {st['confidence']:.2f}" + (" (in tenuta...)" if st["holding"] else "")
        f9 = "F9 globale" if self.hotkey.ok else "F9 (solo con finestra attiva)"
        self.status_label.config(text=f"Webcam: {st['camera']}\nFPS: {st['fps']:.1f}   Fase: {st['phase']}\n"
                                      f"Riconoscimento: {recog}\nScorciatoia: {f9}")
        self.conf_bar["value"] = st["confidence"]
        if st["background"]:
            self.bg_label.config(text="Sfondo calibrato: la persona sparisce durante la sostituzione.", fg="#1a9e3a")
        else:
            self.bg_label.config(text="Sfondo NON calibrato: modalita' semplificata, resti visibile dietro al "
                                      "tronco. Usa 'Calibra sfondo' per la scomparsa completa.", fg="#c05000")
        while not p.events.empty():
            level, text = p.events.get_nowait()
            {"info": messagebox.showinfo, "warning": messagebox.showwarning}.get(level, messagebox.showerror)(
                "ShinobiCam", text)

    def on_close(self) -> None:
        try:
            self.pipeline.stop()
            self.hotkey.close()
            self.settings.save()
        finally:
            self.root.destroy()


def run() -> None:
    root = tk.Tk()
    try:
        from .config import resource_path
        root.iconbitmap(str(resource_path("assets/icon.ico")))
    except tk.TclError:
        pass  # .ico unsupported outside Windows
    App(root)
    log.info("dati utente in %s", data_dir())
    root.mainloop()
