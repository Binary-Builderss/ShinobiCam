"""Tkinter GUI: guided setup checklist, live preview with on-air badge, non-blocking notifications."""
from __future__ import annotations

import logging
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from .camera_manager import is_virtual, list_cameras
from .config import BACKENDS, FPS_CHOICES, RESOLUTIONS, Settings, data_dir, resource_path
from .hotkey import GlobalHotkey
from .pipeline import Pipeline
from .virtual_camera import VirtualCameraError, obs_running

log = logging.getLogger(__name__)

C = {
    "bg": "#121419", "panel": "#1b1e25", "card": "#232731", "line": "#313643", "fg": "#eceef2",
    "muted": "#98a0ad", "accent": "#e87a30", "accent_hi": "#ec8e51", "ok": "#35c46a", "warn": "#f2a531",
    "err": "#e05252", "live": "#c62828", "live_hi": "#a91f1f", "ink": "#15120e", "video": "#0b0c10",
}
TOAST_COLORS = {"info": C["ok"], "warning": C["warn"], "error": C["err"]}
TOAST_SECONDS = {"info": 6, "warning": 10, "error": 0}  # 0 = stays until closed or replaced
THUMB = (160, 90)
NO_SHORTCUT = ("TButton", "TCheckbutton", "TCombobox", "Button", "TScale")  # widgets that use Space/Esc themselves


def to_photo(img, w: int, h: int) -> ImageTk.PhotoImage:
    """BGR array fitted inside w x h."""
    fh, fw = img.shape[:2]
    k = min(w / fw, h / fh)
    small = cv2.resize(img, (max(int(fw * k), 1), max(int(fh * k), 1)), interpolation=cv2.INTER_AREA)
    return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))


def apply_theme(root: tk.Tk) -> dict[str, tkfont.Font]:
    base = tkfont.nametofont("TkDefaultFont")
    size = base.cget("size") or 12
    fonts = {
        "title": tkfont.Font(root, family=base.cget("family"), size=abs(size) + 6, weight="bold"),
        "h": tkfont.Font(root, family=base.cget("family"), size=abs(size) + 1, weight="bold"),
        "small": tkfont.Font(root, family=base.cget("family"), size=max(abs(size) - 1, 9)),
        "badge": tkfont.Font(root, family=base.cget("family"), size=abs(size), weight="bold"),
        "mono": tkfont.Font(root, family="Consolas" if sys.platform == "win32" else tkfont.nametofont("TkFixedFont").cget("family"),
                            size=max(abs(size) - 1, 9)),  # fixed-width digits: FPS/confidence don't jitter
    }
    st = ttk.Style(root)
    st.theme_use("clam")  # the only built-in theme that honours custom colours on Windows and macOS
    root.configure(bg=C["bg"])
    st.configure(".", background=C["panel"], foreground=C["fg"], fieldbackground=C["card"], bordercolor=C["line"],
                 lightcolor=C["panel"], darkcolor=C["panel"], troughcolor=C["card"], focuscolor=C["accent"],
                 selectbackground=C["accent"], selectforeground=C["ink"], insertcolor=C["fg"])
    st.configure("Bg.TFrame", background=C["bg"])
    st.configure("Card.TFrame", background=C["card"])
    st.configure("Muted.TLabel", foreground=C["muted"])
    st.configure("Card.TLabel", background=C["card"])
    st.configure("CardMuted.TLabel", background=C["card"], foreground=C["muted"], font=fonts["small"])
    st.configure("Section.TLabel", font=fonts["h"])
    st.configure("Title.TLabel", background=C["bg"], font=fonts["title"])
    st.configure("Sub.TLabel", background=C["bg"], foreground=C["muted"])
    st.configure("TButton", background=C["card"], foreground=C["fg"], padding=(12, 7), borderwidth=0)
    st.map("TButton", background=[("disabled", C["panel"]), ("pressed", C["line"]), ("active", C["line"])],
           foreground=[("disabled", C["muted"])])
    st.configure("Accent.TButton", background=C["accent"], foreground=C["ink"], font=fonts["h"], padding=(14, 10),
                 focuscolor=C["ink"])
    st.map("Accent.TButton", background=[("disabled", C["card"]), ("pressed", C["accent_hi"]), ("active", C["accent_hi"])],
           foreground=[("disabled", C["muted"])])
    st.configure("Danger.TButton", background=C["live"], foreground=C["fg"], font=fonts["h"], padding=(14, 10),
                 focuscolor=C["fg"])
    st.map("Danger.TButton", background=[("pressed", C["live_hi"]), ("active", C["live_hi"])])
    st.configure("Step.TButton", background=C["line"], padding=(10, 5))
    st.map("Step.TButton", background=[("disabled", C["panel"]), ("pressed", "#454b5b"), ("active", "#3c4250")])
    st.configure("Link.TButton", background=C["panel"], foreground=C["muted"], padding=(4, 2))
    st.map("Link.TButton", background=[("active", C["panel"])], foreground=[("active", C["fg"])])
    st.configure("TCheckbutton", background=C["panel"], foreground=C["fg"])
    st.map("TCheckbutton", background=[("active", C["panel"])],
           indicatorcolor=[("selected", C["accent"]), ("!selected", C["card"])])
    st.configure("TCombobox", fieldbackground=C["card"], background=C["card"], foreground=C["fg"], arrowcolor=C["fg"],
                 padding=4)
    st.map("TCombobox", fieldbackground=[("readonly", C["card"]), ("disabled", C["panel"])],
           foreground=[("disabled", C["muted"])], selectbackground=[("readonly", C["card"])],
           selectforeground=[("readonly", C["fg"])], arrowcolor=[("disabled", C["muted"])])
    st.configure("Horizontal.TScale", background=C["accent"], troughcolor=C["card"], bordercolor=C["panel"])
    for cls in ("TButton", "TCheckbutton", "Button"):
        root.option_add(f"*{cls}.cursor", "hand2")
    root.option_add("*TCombobox*Listbox.background", C["card"])
    root.option_add("*TCombobox*Listbox.foreground", C["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["ink"])
    return fonts


class Step:
    """One row of the setup checklist: badge (number or tick), title, status line, action button."""

    def __init__(self, parent, number: int, title: str, button: str | None, command, fonts):
        self.number = number
        self.frame = ttk.Frame(parent, style="Card.TFrame", padding=(10, 8))
        self.frame.pack(fill="x", pady=3)
        self.frame.columnconfigure(1, weight=1)
        self.badge = tk.Label(self.frame, width=2, font=fonts["badge"], bg=C["line"], fg=C["fg"])
        self.badge.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        ttk.Label(self.frame, text=title, style="Card.TLabel", font=fonts["h"]).grid(row=0, column=1, sticky="w")
        self.status = ttk.Label(self.frame, style="CardMuted.TLabel", wraplength=230, justify="left")
        self.status.grid(row=1, column=1, sticky="w")
        self.thumb = tk.Label(self.frame, bd=0, bg=C["card"])
        self._thumb_src = None
        self._photo = None
        self.button = None
        if button:
            self.button = ttk.Button(self.frame, text=button, style="Step.TButton", command=command)
            self.button.grid(row=0, column=2, rowspan=2, padx=(8, 0))

    def set(self, state: str, text: str, enabled: bool = True) -> None:
        """state: 'done' | 'todo' | 'busy' | 'warn'."""
        badge = {"done": ("✓", C["ok"], C["ink"]), "busy": ("…", C["accent"], C["ink"]),
                 "warn": ("!", C["warn"], C["ink"])}.get(state, (str(self.number), C["line"], C["fg"]))
        self.badge.config(text=badge[0], bg=badge[1], fg=badge[2])
        self.status.config(text=text)
        if self.button:
            self.button.config(state="normal" if enabled else "disabled")

    def set_thumb(self, img) -> None:
        """BGR array or None. Rebuilt only when a different array is passed (callers replace, never mutate)."""
        if img is self._thumb_src:
            return
        self._thumb_src = img
        if img is None:
            self._photo = None
            self.thumb.grid_remove()
            return
        self._photo = to_photo(img, *THUMB)
        self.thumb.config(image=self._photo)
        self.thumb.grid(row=2, column=1, sticky="w", pady=(6, 0))


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings.load()
        self.pipeline = Pipeline(self.settings)
        self.cameras: list[tuple[int, str]] = []
        self._photo = None
        self._preview_seq = 0
        self._ticks = 0
        self._toast_job = None
        self.toast_text = ""
        self.settings_win: tk.Toplevel | None = None
        self.mini: tk.Toplevel | None = None
        self.compact = False

        root.title("ShinobiCam")
        root.minsize(1060, 640)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.fonts = apply_theme(root)
        self._build()
        self.hotkey = GlobalHotkey(self.pipeline.trigger_manual)
        self._bind_keys(root)
        self.refresh_cameras()
        self._sync_running()
        self._refresh_status()
        self._tick()
        if self.settings.autostart:
            root.after(300, lambda: self.start(True))

    def _bind_keys(self, win) -> None:
        def key(action):
            def handler(e):
                if e.widget.winfo_class() not in NO_SHORTCUT:
                    action()
            return handler
        win.bind("<space>", key(self.test_jutsu))
        win.bind("<Escape>", key(self.restore_normal))
        if not self.hotkey.ok:
            win.bind("<F9>", lambda e: self.pipeline.trigger_manual())  # only while this window has focus

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        root = self.root
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, style="Bg.TFrame", padding=(18, 14, 18, 6))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="ShinobiCam", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="  Kawarimi no Jutsu", style="Sub.TLabel").grid(row=0, column=1, sticky="w")
        self.onair = tk.Label(header, font=self.fonts["badge"], padx=12, pady=5)
        self.onair.grid(row=0, column=2, sticky="e")

        side = ttk.Frame(root, padding=14)
        side.grid(row=1, column=0, sticky="ns", padx=(14, 0), pady=(0, 14))

        steps = ttk.Frame(side)
        steps.pack(fill="x")
        self.step_start = Step(steps, 1, "Avvia la webcam", None, None, self.fonts)
        cam_row = ttk.Frame(self.step_start.frame, style="Card.TFrame")
        cam_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.cam_var = tk.StringVar()
        self.cam_box = ttk.Combobox(cam_row, textvariable=self.cam_var, state="readonly", width=26)
        self.cam_box.pack(side="left", fill="x", expand=True)
        self.btn_refresh = ttk.Button(cam_row, text="↻", width=3, style="Step.TButton", command=self.refresh_cameras)
        self.btn_refresh.pack(side="left", padx=(6, 0))

        self.btn_main = ttk.Button(self.step_start.frame, style="Accent.TButton")
        self.btn_main.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.btn_sim = ttk.Button(self.step_start.frame, text="Solo anteprima (non va in onda)", style="Step.TButton",
                                  command=lambda: self.start(False))
        self.btn_sim.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        self.step_bg = Step(steps, 2, "Calibra lo sfondo", "Calibra", self.calibrate_bg, self.fonts)
        self.step_seal = Step(steps, 3, "Registra il sigillo", "Registra", self.record_seal, self.fonts)
        self.step_app = Step(steps, 4, "Usala in Teams o Discord", None, None, self.fonts)

        ttk.Label(side, text="Jutsu", style="Section.TLabel").pack(anchor="w", pady=(14, 0))
        jutsu = ttk.Frame(side)
        jutsu.pack(fill="x", pady=(4, 0))
        jutsu.columnconfigure((0, 1), weight=1)
        ttk.Button(jutsu, text="Testa sostituzione", command=self.test_jutsu).grid(row=0, column=0, sticky="ew")
        ttk.Button(jutsu, text="Webcam normale", command=self.restore_normal).grid(row=0, column=1, sticky="ew",
                                                                                 padx=(6, 0))
        self.recog_var = tk.BooleanVar(value=self.settings.recognition_enabled)
        ttk.Checkbutton(jutsu, text="Riconosci il sigillo automaticamente", variable=self.recog_var,
                        command=self._apply_live).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.hotkey_label = ttk.Label(jutsu, style="Muted.TLabel", font=self.fonts["small"])
        self.hotkey_label.grid(row=2, column=0, columnspan=2, sticky="w")

        links = ttk.Frame(side)
        links.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(links, text="Impostazioni", style="Link.TButton", command=self.open_settings).pack(side="left")
        ttk.Button(links, text="Modalità compatta", style="Link.TButton", command=self.enter_compact).pack(
            side="right")

        main = ttk.Frame(root, style="Bg.TFrame", padding=(14, 0, 18, 14))
        main.grid(row=1, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        # Fixed-size container: the image is fitted to it, never the other way round
        # (a Label sized by its image grows the window on every frame).
        self.preview_box = tk.Frame(main, bg=C["video"], width=720, height=405)
        self.preview_box.grid(row=0, column=0, sticky="nsew")
        self.preview_box.grid_propagate(False)
        self.preview = tk.Label(self.preview_box, bg=C["video"], fg=C["muted"], font=self.fonts["h"], bd=0,
                                text="Anteprima spenta\n\nScegli la webcam e premi «Avvia webcam virtuale»")
        self.preview.place(relx=0.5, rely=0.5, anchor="center")

        strip = ttk.Frame(main, padding=(12, 8))
        strip.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        strip.columnconfigure(1, weight=1)
        ttk.Label(strip, text="Sigillo", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.meter = tk.Canvas(strip, height=16, bg=C["card"], highlightthickness=0)
        self.meter.grid(row=0, column=1, sticky="ew")
        self.meter_label = ttk.Label(strip, width=28, anchor="e", font=self.fonts["mono"])
        self.meter_label.grid(row=0, column=2, sticky="e", padx=(10, 0))
        self.info_label = ttk.Label(strip, style="Muted.TLabel", font=self.fonts["mono"])
        self.info_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.toast = tk.Frame(main, bg=C["card"])
        self.toast.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.toast.columnconfigure(1, weight=1)
        self.toast_bar = tk.Frame(self.toast, width=5, bg=C["ok"])
        self.toast_bar.grid(row=0, column=0, sticky="ns")
        self.toast_label = tk.Label(self.toast, bg=C["card"], fg=C["fg"], justify="left", anchor="w",
                                    wraplength=640, padx=12, pady=10)
        self.toast_label.grid(row=0, column=1, sticky="ew")
        tk.Button(self.toast, text="✕", command=self.hide_toast, bg=C["card"], fg=C["muted"], relief="flat",
                  bd=0, highlightthickness=0, activebackground=C["line"], activeforeground=C["fg"]).grid(row=0, column=2, padx=8)
        self.toast.grid_remove()

    # ------------------------------------------------------------ settings window
    def open_settings(self) -> None:
        if self.settings_win is not None:
            self.settings_win.deiconify()
            self.settings_win.lift()
            return
        s = self.settings
        win = self.settings_win = tk.Toplevel(self.root, bg=C["panel"])
        win.title("Impostazioni - ShinobiCam")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        win.bind("<Escape>", lambda e: win.withdraw())
        body = ttk.Frame(win, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        rows = iter(range(100))

        def full(widget, pady=0):
            widget.grid(row=next(rows), column=0, columnspan=3, sticky="w", pady=pady)

        full(ttk.Label(body, text="Video", style="Section.TLabel"))
        self.res_var = tk.StringVar(value=f"{s.width}x{s.height}")
        self.fps_var = tk.StringVar(value=str(s.fps))
        self.backend_var = tk.StringVar(value=s.backend)
        self.video_boxes = []
        for label, var, values in [("Risoluzione", self.res_var, list(RESOLUTIONS)),
                                   ("FPS", self.fps_var, [str(f) for f in FPS_CHOICES]),
                                   ("Webcam virtuale", self.backend_var, list(BACKENDS))]:
            r = next(rows)
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=3)
            box = ttk.Combobox(body, textvariable=var, values=values, state="readonly", width=14)
            box.grid(row=r, column=1, sticky="w", pady=3)
            self.video_boxes.append(box)
        self.video_note = ttk.Label(body, style="Muted.TLabel", font=self.fonts["small"])
        full(self.video_note, (2, 6))
        self.autostart_var = tk.BooleanVar(value=s.autostart)
        full(ttk.Checkbutton(body, text="Avvia la webcam virtuale all'apertura dell'app", variable=self.autostart_var,
                             command=self._apply_live), (0, 14))

        full(ttk.Label(body, text="Riconoscimento ed effetto", style="Section.TLabel"))
        self.thr_var = tk.DoubleVar(value=s.threshold)
        self.cool_var = tk.DoubleVar(value=s.cooldown_s)
        self.sub_var = tk.DoubleVar(value=s.substitution_ms / 1000)
        self.scale_values = []
        for label, hint, var, lo, hi in [
                ("Soglia confidenza", "più alta = meno attivazioni per errore", self.thr_var, 0.3, 0.95),
                ("Pausa dopo il jutsu", "secondi in cui il sigillo è ignorato", self.cool_var, 3.0, 5.0),
                ("Durata del tronco", "secondi", self.sub_var, 1.8, 2.5)]:
            r = next(rows)
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=(6, 0))
            ttk.Scale(body, from_=lo, to=hi, variable=var, length=220,
                      command=lambda _v: self._apply_live()).grid(row=r, column=1, sticky="ew", pady=(6, 0))
            value = ttk.Label(body, width=5, anchor="e", font=self.fonts["mono"])
            value.grid(row=r, column=2, sticky="e", pady=(6, 0))
            self.scale_values.append(value)
            ttk.Label(body, text=hint, style="Muted.TLabel", font=self.fonts["small"]).grid(
                row=next(rows), column=1, sticky="w")
        self.debug_var = tk.BooleanVar(value=s.debug)
        full(ttk.Checkbutton(body, text="Debug: mostra i punti delle mani (solo in questa anteprima)",
                             variable=self.debug_var, command=self._apply_live), (12, 0))

        full(ttk.Label(body, text="Tronco", style="Section.TLabel"), (16, 0))
        self.sprite_label = ttk.Label(body, style="Muted.TLabel", font=self.fonts["small"], wraplength=360)
        full(self.sprite_label)
        buttons = ttk.Frame(body)
        full(buttons, (6, 0))
        ttk.Button(buttons, text="Carica PNG…", command=self.load_sprite).pack(side="left")
        ttk.Button(buttons, text="Predefinito", command=lambda: self.set_sprite("")).pack(side="left", padx=(6, 0))

        full(ttk.Label(body, text=f"Dati salvati in {data_dir()}", style="Muted.TLabel", font=self.fonts["small"],
                       wraplength=400), (16, 0))
        self._apply_live()
        self._sync_running()

    # ------------------------------------------------------------ compact window
    def _build_mini(self) -> None:
        win = self.mini = tk.Toplevel(self.root, bg=C["panel"])
        win.title("ShinobiCam")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self.exit_compact)
        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure((0, 1), weight=1)
        self.mini_onair = tk.Label(body, font=self.fonts["badge"], padx=10, pady=4)
        self.mini_onair.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.mini_meter = tk.Canvas(body, width=300, height=12, bg=C["card"], highlightthickness=0)
        self.mini_meter.grid(row=1, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Button(body, text="Testa sostituzione", style="Step.TButton", command=self.test_jutsu).grid(
            row=2, column=0, sticky="ew")
        ttk.Button(body, text="Webcam normale", style="Step.TButton", command=self.restore_normal).grid(
            row=2, column=1, sticky="ew", padx=(6, 0))
        self.mini_msg = tk.Label(body, bg=C["panel"], fg=C["muted"], font=self.fonts["small"], wraplength=300,
                                 justify="left", anchor="w")
        self.mini_msg.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(body, text="Espandi", style="Link.TButton", command=self.exit_compact).grid(
            row=4, column=0, columnspan=2, sticky="e")
        self._bind_keys(win)

    def enter_compact(self) -> None:
        if self.mini is None:
            self._build_mini()
        self.compact = True
        self.mini_msg.config(text=self.toast_text)
        self.mini.deiconify()
        self.root.withdraw()
        self._refresh_status()

    def exit_compact(self) -> None:
        self.compact = False
        self.root.deiconify()
        self.mini.withdraw()

    # ------------------------------------------------------------ actions
    def refresh_cameras(self) -> None:
        self.cameras = list_cameras()
        values = [n + ("  (virtuale)" if is_virtual(n) else "") for _, n in self.cameras]
        self.cam_box["values"] = values
        current = [v for (i, _), v in zip(self.cameras, values) if i == self.settings.camera_index]
        physical = [v for (i, n), v in zip(self.cameras, values) if not is_virtual(n)]
        self.cam_var.set(current[0] if current and not current[0].endswith("(virtuale)")
                         else (physical or values or [""])[0])
        if not values:
            self.show_toast("warning", "Nessuna webcam trovata. Collegala e premi ↻.")

    def _apply_live(self) -> None:
        s = self.settings
        s.recognition_enabled = self.recog_var.get()
        if self.settings_win is not None:
            s.debug = self.debug_var.get()
            s.autostart = self.autostart_var.get()
            s.threshold = round(self.thr_var.get(), 2)
            s.cooldown_s = round(self.cool_var.get(), 1)
            s.substitution_ms = int(round(self.sub_var.get(), 1) * 1000)
            for lbl, text in zip(self.scale_values, (f"{s.threshold:.2f}", f"{s.cooldown_s:.1f}s",
                                                     f"{s.substitution_ms / 1000:.1f}s")):
                lbl.config(text=text)
            self.sprite_label.config(text=f"In uso: {self.pipeline.sprite_source}")

    def _selected_camera(self) -> tuple[int, str] | None:
        values = list(self.cam_box["values"])
        sel = self.cam_var.get()
        return self.cameras[values.index(sel)] if sel in values else None

    def _apply_start_settings(self) -> bool:
        s = self.settings
        cam = self._selected_camera()
        if cam is None:
            self.show_toast("error", "Nessuna webcam selezionata. Collegala e premi ↻.")
            return False
        if is_virtual(cam[1]):
            self.show_toast("error", "Hai scelto una webcam virtuale come sorgente. Scegli la webcam fisica, "
                                     "altrimenti l'immagine entra in loop.")
            return False
        s.camera_index = cam[0]
        if self.settings_win is not None:
            s.width, s.height = RESOLUTIONS[self.res_var.get()]
            s.fps = int(self.fps_var.get())
            s.backend = self.backend_var.get()
        self._apply_live()
        s.save()
        return True

    def start(self, use_vcam: bool) -> None:
        if not self._apply_start_settings():
            return
        if use_vcam and obs_running() and not messagebox.askokcancel(
                "OBS è aperto",
                "OBS Studio è aperto. Se la sua webcam virtuale è attiva, Teams e Discord vedranno OBS "
                "al posto di ShinobiCam, senza alcun messaggio di errore.\n\n"
                "Chiudi OBS (Cmd+Q) e premi OK per avviare.", icon="warning"):
            return
        self.preview.config(image="", text="Avvio della webcam…")
        self.root.update_idletasks()
        try:
            self.pipeline.start(use_virtual_camera=use_vcam)
        except VirtualCameraError as e:
            self.stop()
            self.show_toast("error", str(e))
            return
        except Exception as e:
            log.exception("avvio")
            self.stop()
            self.show_toast("error", f"Avvio fallito: {e}")
            return
        self._sync_running()
        self._refresh_status()

    def stop(self) -> None:
        self.pipeline.stop()
        self._sync_running()
        self._photo = None
        self.preview.config(image="", text="Anteprima spenta")
        self._refresh_status()

    def _sync_running(self) -> None:
        running = self.pipeline.running
        if running:
            self.btn_main.config(text="Arresta", style="Danger.TButton", command=self.stop)
        else:
            self.btn_main.config(text="Avvia webcam virtuale", style="Accent.TButton", command=lambda: self.start(True))
        self.btn_sim.config(state="disabled" if running else "normal")
        self.btn_refresh.config(state="disabled" if running else "normal")
        self.cam_box.config(state="disabled" if running else "readonly")
        if self.settings_win is not None:
            for box in self.video_boxes:
                box.config(state="disabled" if running else "readonly")
            self.video_note.config(text="Arresta la webcam per modificare queste opzioni." if running
                                   else "Si applicano al prossimo avvio. 640×360 per PC lenti.")

    def test_jutsu(self) -> None:
        if not self.pipeline.running:
            self.show_toast("warning", "Avvia prima la webcam (passo 1).")
            return
        self.pipeline.trigger_manual()

    def record_seal(self) -> None:
        if not self.pipeline.running:
            self.show_toast("warning", "Avvia prima la webcam (passo 1).")
            return
        if not self.pipeline.start_gesture_recording():
            self.show_toast("error", f"Riconoscimento non disponibile: {self.pipeline.recognition_error}\n"
                                     "Puoi comunque usare «Testa sostituzione» o F9.")
            return
        self.show_toast("info", "Tra 3 secondi esegui il sigillo e tienilo per 4 secondi, muovendo leggermente "
                                "le mani. Segui il conto alla rovescia nell'anteprima.")

    def calibrate_bg(self) -> None:
        self.pipeline.start_background_capture()
        self.show_toast("info", "Hai 5 secondi per uscire dall'inquadratura. Non muovere la webcam" +
                        (" (sul MacBook: non toccare lo schermo)." if sys.platform == "darwin" else "."))

    def restore_normal(self) -> None:
        self.pipeline.reset_effect()
        self.recog_var.set(False)
        self._apply_live()
        self.show_toast("info", "Webcam normale: effetto interrotto e riconoscimento automatico disattivato.")

    def load_sprite(self) -> None:
        path = filedialog.askopenfilename(title="PNG del tronco (con trasparenza)", filetypes=[("PNG", "*.png")])
        if path:
            self.set_sprite(path)

    def set_sprite(self, path: str) -> None:
        src = self.pipeline.set_log_sprite(path)
        if path and src != path:
            self.show_toast("warning", "Immagine non valida: uso il tronco predefinito.")
            path = ""
        self.settings.log_image = path
        self.settings.save()
        self._apply_live()

    # ------------------------------------------------------------ notifications
    def show_toast(self, level: str, text: str) -> None:
        self.toast_text = text
        self.toast_bar.config(bg=TOAST_COLORS.get(level, C["err"]))
        self.toast_label.config(text=text)
        self.toast.grid()
        if self.mini is not None:
            self.mini_msg.config(text=text, fg=TOAST_COLORS.get(level, C["err"]))
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
            self._toast_job = None
        if TOAST_SECONDS.get(level, 0):
            self._toast_job = self.root.after(TOAST_SECONDS[level] * 1000, self.hide_toast)

    def hide_toast(self) -> None:
        self._toast_job = None
        self.toast_text = ""
        self.toast.grid_remove()
        if self.mini is not None:
            self.mini_msg.config(text="")

    # ------------------------------------------------------------ periodic refresh
    def _tick(self) -> None:
        try:
            seq, frame, _ = self.pipeline.preview.peek()
            if frame is not None and seq != self._preview_seq and self.pipeline.running:
                self._preview_seq = seq
                if not self.compact:  # hidden window: skip the resize work
                    self._photo = to_photo(frame, max(self.preview_box.winfo_width(), 320),
                                           max(self.preview_box.winfo_height(), 180))
                    self.preview.config(image=self._photo, text="")
            self._ticks += 1
            if self._ticks % 4 == 0:
                self._refresh_status()
        except Exception:
            log.exception("aggiornamento UI")
        self.root.after(30, self._tick)

    @staticmethod
    def _draw_meter(m: tk.Canvas, conf: float, threshold: float, active: bool) -> None:
        m.delete("all")
        w, h = max(m.winfo_width(), 100), int(m.cget("height"))
        if active:
            color = C["ok"] if conf >= threshold else C["accent"]
            m.create_rectangle(0, 0, int(w * conf), h, fill=color, width=0)
        x = int(w * threshold)
        m.create_line(x, 0, x, h, fill=C["fg"], width=2)

    def _refresh_status(self) -> None:
        p, s = self.pipeline, self.settings
        st = p.status()
        running = p.running

        if st["vcam"]:
            badge = dict(text=f"●  IN ONDA · {st['vcam']}", bg=C["live"], fg=C["fg"])
        elif running:
            badge = dict(text="SOLO ANTEPRIMA · non va in onda", bg=C["warn"], fg=C["ink"])
        else:
            badge = dict(text="SPENTO", bg=C["card"], fg=C["muted"])
        self.onair.config(**badge)
        if self.compact:
            self.mini_onair.config(**badge)

        if not running:
            self.step_start.set("todo", "Scegli la webcam fisica (non quella virtuale).")
        elif "connessa" not in st["camera"]:
            self.step_start.set("warn", f"Webcam: {st['camera']}")
        else:
            self.step_start.set("done", f"Webcam connessa · {st['fps']:.0f} FPS")

        if st["capturing_background"]:
            self.step_bg.set("busy", "Esci dall'inquadratura…", enabled=False)
        elif st["background"]:
            self.step_bg.set("done", "Calibrato. Ricalibra se sposti la webcam o cambia la luce.", running)
        elif st["background_other_res"]:
            self.step_bg.set("warn", "Sfondo registrato a un'altra risoluzione: ricalibra.", running)
        else:
            self.step_bg.set("warn", "Non calibrato: resti visibile dietro al tronco." +
                             ("" if running else " Avvia prima la webcam."), running)

        self.step_bg.set_thumb(p.background.plate)
        self.step_seal.set_thumb(p.seal_image if st["profile"] else None)

        if st["recognition_error"]:
            self.step_seal.set("warn", "Riconoscimento non disponibile: usa «Testa sostituzione» o F9.", False)
        elif st["recording_seal"]:
            self.step_seal.set("busy", "Esegui il sigillo e tienilo…", enabled=False)
        elif st["profile"]:
            self.step_seal.set("done", "Registrato. La foto ti ricorda la posa.", running)
        else:
            self.step_seal.set("todo", "Nessun sigillo registrato." + ("" if running else " Avvia prima la webcam."),
                               running)

        if st["vcam"]:
            self.step_app.set("done", f"Scegli la fotocamera «{st['vcam']}» nelle impostazioni video.")
        else:
            self.step_app.set("todo", "Dopo l'avvio, scegli «OBS Virtual Camera» come fotocamera.")

        recog_active = running and s.recognition_enabled and st["profile"] and not st["recognition_error"]
        for canvas in (self.meter, self.mini_meter) if self.compact else (self.meter,):
            self._draw_meter(canvas, st["confidence"], s.threshold, bool(recog_active))
        if not running:
            meter_text = ""
        elif not s.recognition_enabled:
            meter_text = "riconoscimento spento"
        elif not st["profile"]:
            meter_text = "nessun sigillo"
        else:
            meter_text = f"{st['confidence']:.2f} / soglia {s.threshold:.2f}" + ("  in tenuta" if st["holding"] else "")
        self.meter_label.config(text=meter_text)
        phase = {"IDLE": "pronto", "SMOKE_IN": "fumo", "SUBSTITUTION": "tronco", "SMOKE_OUT": "fumo",
                 "COOLDOWN": "pausa"}.get(st["phase"], st["phase"])
        self.info_label.config(text=f"FPS {st['fps']:.0f}      Jutsu: {phase}      Webcam: {st['camera']}"
                               if running else "")
        f9 = ("F9 funziona anche con Teams in primo piano." if self.hotkey.ok else
              "fn+F9 funziona solo con questa finestra attiva." if sys.platform == "darwin" else
              "F9 funziona solo con questa finestra attiva.")
        self.hotkey_label.config(text=f"{f9}\nSpazio: testa sostituzione.  Esc: webcam normale.")

        while not p.events.empty():
            level, text = p.events.get_nowait()
            self.show_toast(level, text)

    def on_close(self) -> None:
        try:
            self.pipeline.stop()
            self.hotkey.close()
            self.settings.save()
        finally:
            self.root.destroy()


def run() -> None:
    if sys.platform == "win32":
        try:  # without this Windows bitmap-scales the whole window at 125-150% and text looks blurry
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            log.warning("DPI awareness non impostata")
    root = tk.Tk()
    try:
        if sys.platform == "win32":
            root.iconbitmap(str(resource_path("assets/icon.ico")))
        else:
            root.iconphoto(True, tk.PhotoImage(file=str(resource_path("assets/log.png"))))
    except tk.TclError:
        log.warning("icona finestra non caricata")
    App(root)
    log.info("dati utente in %s", data_dir())
    root.mainloop()
