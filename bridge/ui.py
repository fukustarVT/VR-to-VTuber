import os
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk

import bridge.state as state
from bridge.head import recenter
from bridge.paths import app_dir
from bridge.settings import PRESETS, ensure_loaded, read_endpoint, save, set_destination
from bridge.update import VERSION

BG = "#16161c"
CARD = "#22222b"
TEXT = "#f4f1ea"
MUTED = "#a8a3b5"
GREEN = "#7dce7a"
AMBER = "#e2b656"
RED = "#e07a7a"
INK = "#14210f"

COPY = {
    "vts": {
        "subtitle": "Sending data from VR to VTube Studio",
        "steps": (
            "You will need SteamVR, VRCFaceTracking, and VTube Studio.\n"
            "1. Start SteamVR with your headset on.\n"
            "2. Press Start and look straight ahead.\n"
            "3. Open VRCFaceTracking.\n"
            "4. In VTube Studio, turn on Start API. Leave the port at 8001.\n"
            "5. Allow VR to VTuber the first time it asks."
        ),
    },
    "ifm": {
        "subtitle": "Sending data from VR as iFacialMocap",
        "steps": (
            "You will need SteamVR, VRCFaceTracking, and an app that receives iFacialMocap data.\n"
            "1. Start SteamVR with your headset on.\n"
            "2. Press Start and look straight ahead.\n"
            "3. Open VRCFaceTracking.\n"
            "4. VMagicMirror: Face Tracking, iFacialMocap. Enter the address below and press Connect. Turn on Perfect Sync.\n"
            "5. Warudo: add an iFacialMocap Receiver and set its port to the port below."
        ),
    },
}

LINKS = {
    "vts": [
        ("Get SteamVR", "https://store.steampowered.com/app/250820/SteamVR/"),
        ("Get VRCFaceTracking", "https://vrcft.io/"),
        ("Get VTube Studio", "https://denchisoft.com/"),
    ],
    "ifm": [
        ("Get SteamVR", "https://store.steampowered.com/app/250820/SteamVR/"),
        ("Get VRCFaceTracking", "https://vrcft.io/"),
    ],
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        ensure_loaded()
        self.title(f"VR to VTuber {VERSION}")
        self.configure(bg=BG)
        self._set_icon()
        self.geometry("560x760")
        self.minsize(530, 560)
        self._locking = False
        self.worker = None
        self.running = False
        self.vars = {}
        self.tune_open = False

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(self.canvas, bg=BG)
        self._window = self.canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._wheel)

        tk.Label(body, text=f"VR to VTuber {VERSION}", bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=24, pady=(22, 2))
        self.subtitle = tk.Label(body, text="", bg=BG, fg=MUTED, font=("Segoe UI", 11), justify="left")
        self.subtitle.pack(anchor="w", padx=24, pady=(0, 12))

        self.update_lbl = tk.Label(
            body, text="Update available", bg=BG, fg=AMBER, cursor="hand2",
            font=("Segoe UI", 11, "underline"),
        )
        self.switch = tk.Frame(body, bg=BG)
        self.switch.pack(fill="x", padx=24, pady=(0, 4))
        self.dest_btns = {}
        for key, label in (("vts", "VTube Studio"), ("ifm", "iFacialMocap")):
            btn = tk.Button(
                self.switch, text=label, command=lambda k=key: self.choose(k),
                font=("Segoe UI", 12, "bold"), relief="flat", padx=12, pady=8,
            )
            btn.pack(side="left", expand=True, fill="x", padx=(0, 8) if key == "vts" else 0)
            self.dest_btns[key] = btn
        tk.Label(
            body, text="Tracking status",
            bg=BG, fg=MUTED, font=("Segoe UI", 12),
        ).pack(anchor="w", padx=24, pady=(0, 12))

        card = tk.Frame(body, bg=CARD)
        card.pack(fill="x", padx=24, pady=(0, 14))
        self.dots = {}
        self.labels = {}
        self.output_title = None
        for key, title in (("headset", "Neck"), ("tracking", "Face tracking"), ("output", "VTube Studio")):
            row = tk.Frame(card, bg=CARD)
            row.pack(fill="x", padx=16, pady=8)
            dot = tk.Label(row, text="\u25cf", bg=CARD, fg=MUTED, font=("Segoe UI", 16))
            dot.pack(side="left")
            title_lbl = tk.Label(row, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 12, "bold"), width=16, anchor="w")
            title_lbl.pack(side="left", padx=(8, 0))
            value = tk.Label(row, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 11), anchor="w")
            value.pack(side="left")
            self.dots[key] = dot
            self.labels[key] = value
            if key == "output":
                self.output_title = title_lbl

        self.steps = tk.Label(body, text="", bg=BG, fg=TEXT, font=("Segoe UI", 11), justify="left", anchor="w", wraplength=500)
        self.steps.pack(anchor="w", padx=24, pady=(0, 6))

        self.endpoint = tk.Frame(body, bg=BG)
        tk.Label(self.endpoint, text="Send to", bg=BG, fg=TEXT, font=("Segoe UI", 11)).pack(side="left")
        self.host_var = tk.StringVar(value=state.ifm_host)
        self.port_var = tk.StringVar(value=str(state.ifm_port))
        host = tk.Entry(self.endpoint, textvariable=self.host_var, bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat", width=16, font=("Segoe UI", 11))
        host.pack(side="left", padx=(8, 4), ipady=4)
        tk.Label(self.endpoint, text=":", bg=BG, fg=MUTED, font=("Segoe UI", 12, "bold")).pack(side="left")
        port = tk.Entry(self.endpoint, textvariable=self.port_var, bg=CARD, fg=TEXT, insertbackground=TEXT, relief="flat", width=7, font=("Segoe UI", 11))
        port.pack(side="left", padx=(4, 0), ipady=4)
        self.host_var.trace_add("write", lambda *_a: self._read_endpoint())
        self.port_var.trace_add("write", lambda *_a: self._read_endpoint())

        self.links = tk.Frame(body, bg=BG)
        self.links.pack(anchor="w", padx=24, pady=(0, 8))

        self.tune_btn = tk.Button(
            body, text="Adjustments   \u25b8", command=self.toggle_tune,
            bg=BG, fg=TEXT, activebackground=BG, activeforeground=TEXT,
            font=("Segoe UI", 13, "bold"), relief="flat", anchor="w", padx=0,
        )
        self.tune_btn.pack(fill="x", padx=24, pady=(8, 0))

        self.tune = tk.Frame(body, bg=BG)
        self._slider(self.tune, "Neck amount", 0.15, 1.0, state.HEAD_GAIN, "HEAD_GAIN", "Calmer", "Stronger")
        self._slider(self.tune, "Eye size", 0.15, 0.9, state.EYE_REST, "EYE_REST", "Smaller", "Wider")
        self._slider(self.tune, "Eye movement", 0.3, 1.6, state.EYE_GAZE, "EYE_GAZE", "Less", "More")
        self._slider(self.tune, "Mouth open", 0.3, 1.8, state.MOUTH_GAIN, "MOUTH_GAIN", "Less", "More")
        self._slider(self.tune, "Smile", 0.15, 0.85, state.SMILE_REST, "SMILE_REST", "Frown", "Smile")
        self._slider(self.tune, "Brows", 0.3, 1.8, state.BROW_GAIN, "BROW_GAIN", "Calmer", "Stronger")

        flips = tk.Frame(self.tune, bg=BG)
        flips.pack(anchor="w", pady=(10, 4))
        self.yaw = tk.BooleanVar(value=state.INVERT_YAW)
        self.pitch = tk.BooleanVar(value=state.INVERT_PITCH)
        self.roll = tk.BooleanVar(value=state.INVERT_ROLL)
        for text, var, attr in (
            ("Flip turn", self.yaw, "INVERT_YAW"),
            ("Flip nod", self.pitch, "INVERT_PITCH"),
            ("Flip tilt", self.roll, "INVERT_ROLL"),
        ):
            tk.Checkbutton(
                flips, text=text, variable=var, command=lambda a=attr, v=var: setattr(state, a, bool(v.get())),
                bg=BG, fg=TEXT, selectcolor=CARD, activebackground=BG, activeforeground=TEXT,
                font=("Segoe UI", 10),
            ).pack(side="left", padx=(0, 12))

        buttons = tk.Frame(body, bg=BG)
        buttons.pack(fill="x", padx=24, pady=(12, 8))
        self.start_btn = tk.Button(buttons, text="Start", command=self.start, bg=GREEN, fg=INK, font=("Segoe UI", 13, "bold"), relief="flat", padx=18, pady=8)
        self.start_btn.pack(side="left")
        self.stop_btn = tk.Button(buttons, text="Stop", command=self.stop, bg=CARD, fg=TEXT, activebackground=CARD, activeforeground=TEXT, font=("Segoe UI", 13), relief="flat", padx=18, pady=8)
        self.stop_btn.pack(side="left", padx=8)
        tk.Button(buttons, text="Reset neck", command=recenter, bg=CARD, fg=TEXT, font=("Segoe UI", 13), relief="flat", padx=18, pady=8).pack(side="left")

        self.detail = tk.Label(body, text=state.status["detail"], bg=BG, fg=MUTED, font=("Segoe UI", 11), wraplength=500, justify="left")
        self.detail.pack(anchor="w", padx=24, pady=(8, 24))
        self._body = body
        self._sync_widgets()
        self.after(400, self.refresh)
        self.after(50, self._lock_size)
        self._check_update()
        self.bind("<Configure>", self._guard_size)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _lock_size(self):
        self.update_idletasks()
        width = max(530, self._body.winfo_reqwidth() + 28)
        height = 560
        self.minsize(width, height)
        if self.winfo_width() < width or self.winfo_height() < height:
            self._locking = True
            self.geometry(f"{max(self.winfo_width(), width)}x{max(self.winfo_height(), 760)}")
            self._locking = False

    def _guard_size(self, event):
        if event.widget is not self or self._locking:
            return
        min_w, min_h = self.minsize()
        if event.width < min_w or event.height < min_h:
            self._locking = True
            self.geometry(f"{max(event.width, min_w)}x{max(event.height, min_h)}")
            self._locking = False

    def _link(self, parent, text, url):
        label = tk.Label(parent, text=text, bg=BG, fg="#9eb6ff", cursor="hand2", font=("Segoe UI", 11, "underline"))
        label.pack(side="left")
        label.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))

    def _icon_file(self):
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base = app_dir()
        return os.path.join(base, "icon.ico")

    def _set_icon(self):
        path = self._icon_file()
        if not os.path.exists(path):
            return
        try:
            self.iconbitmap(default=path)
        except tk.TclError:
            try:
                self.iconbitmap(path)
            except tk.TclError:
                pass

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _fill_links(self):
        for child in self.links.winfo_children():
            child.destroy()
        for index, (text, url) in enumerate(LINKS[state.destination]):
            if index:
                tk.Label(self.links, text="   ", bg=BG).pack(side="left")
            self._link(self.links, text, url)

    def _show_endpoint(self):
        if state.destination == "ifm":
            if not self.endpoint.winfo_ismapped():
                self.endpoint.pack(fill="x", padx=24, pady=(0, 8), before=self.links)
        else:
            self.endpoint.pack_forget()

    def _style_dest(self):
        for key, btn in self.dest_btns.items():
            on = key == state.destination
            if self.running and not on:
                btn.configure(state="disabled", bg=CARD, fg=MUTED, disabledforeground=MUTED)
            else:
                btn.configure(
                    state="normal",
                    bg=GREEN if on else CARD,
                    fg=INK if on else TEXT,
                    activebackground=GREEN if on else CARD,
                    activeforeground=INK if on else TEXT,
                )

    def _style_run(self):
        self.start_btn.configure(state="disabled" if self.running else "normal")
        if self.running:
            self.stop_btn.configure(bg=RED, fg=TEXT, activebackground=RED, activeforeground=TEXT)
        else:
            self.stop_btn.configure(bg=CARD, fg=TEXT, activebackground=CARD, activeforeground=TEXT)
        self._style_dest()

    def _sync_widgets(self):
        for attr, var in self.vars.items():
            var.set(float(getattr(state, attr)))
        self.yaw.set(bool(state.INVERT_YAW))
        self.pitch.set(bool(state.INVERT_PITCH))
        self.roll.set(bool(state.INVERT_ROLL))
        self.host_var.set(state.ifm_host)
        self.port_var.set(str(state.ifm_port))
        copy = COPY[state.destination]
        self.subtitle.configure(text=copy["subtitle"])
        self.steps.configure(text=copy["steps"])
        self.output_title.configure(text=PRESETS[state.destination]["title"])
        self._style_dest()
        self._fill_links()
        self._show_endpoint()

    def _read_endpoint(self):
        read_endpoint(self.host_var.get(), self.port_var.get())

    def choose(self, dest):
        if self.running or dest == state.destination:
            return
        self._apply_sliders()
        self._read_endpoint()
        set_destination(dest)
        self._sync_widgets()

    def toggle_tune(self):
        self.tune_open = not self.tune_open
        if self.tune_open:
            self.tune.pack(fill="x", padx=24, after=self.tune_btn)
            self.tune_btn.configure(text="Adjustments   \u25be")
        else:
            self.tune.pack_forget()
            self.tune_btn.configure(text="Adjustments   \u25b8")

    def _slider(self, parent, label, lo, hi, value, attr, left, right):
        var = tk.DoubleVar(value=value)
        self.vars[attr] = var
        tk.Label(parent, text=label, bg=BG, fg=TEXT, font=("Segoe UI", 11)).pack(anchor="w", pady=(8, 0))
        ttk.Scale(parent, from_=lo, to=hi, variable=var, command=lambda _v, a=attr, s=var: setattr(state, a, float(s.get()))).pack(fill="x")
        ends = tk.Frame(parent, bg=BG)
        ends.pack(fill="x")
        tk.Label(ends, text=left, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(ends, text=right, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

    def _apply_sliders(self):
        for attr, var in self.vars.items():
            setattr(state, attr, float(var.get()))
        state.INVERT_YAW = bool(self.yaw.get())
        state.INVERT_PITCH = bool(self.pitch.get())
        state.INVERT_ROLL = bool(self.roll.get())

    def _persist(self):
        self._apply_sliders()
        self._read_endpoint()
        save()

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        self._persist()
        recenter()

        def go():
            try:
                from bridge.runner import main as run_main
                run_main()
            except Exception as exc:
                state.status["detail"] = "Could not start. The log in the console has the reason."
                print(f"Could not start ({exc}).", flush=True)

        self.worker = threading.Thread(target=go, daemon=True)
        self.worker.start()
        self.running = True
        self._style_run()

    def stop(self):
        self._persist()
        state.stop_event.set()
        self.running = False
        self._style_run()

    def _check_update(self):
        def go():
            from bridge.update import latest_url
            url = latest_url()
            if url:
                self.after(0, lambda: self._show_update(url))

        threading.Thread(target=go, daemon=True).start()

    def _show_update(self, url):
        if not self.winfo_exists():
            return
        self.update_lbl.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
        if not self.update_lbl.winfo_ismapped():
            self.update_lbl.pack(anchor="w", padx=24, pady=(0, 8), before=self.switch)

    def close(self):
        self._persist()
        state.stop_event.set()
        self.destroy()

    def refresh(self):
        for key, label in self.labels.items():
            raw = state.status.get(key, "")
            shown = raw
            if key == "headset" and raw == "Connected" and state.status.get("source"):
                shown = f"Connected ({state.status['source']})"
            label.configure(text=shown)
            if raw == "Connected" or raw.startswith("Connected"):
                color = GREEN
            elif raw.startswith("Waiting"):
                color = AMBER
            else:
                color = RED
            self.dots[key].configure(fg=color)
        self.output_title.configure(text=PRESETS[state.destination]["title"])
        self.detail.configure(text=state.status.get("detail", ""))
        if self.running and self.worker and not self.worker.is_alive():
            self.running = False
            self._style_run()
        self.after(400, self.refresh)


def main():
    ensure_loaded()
    App().mainloop()
