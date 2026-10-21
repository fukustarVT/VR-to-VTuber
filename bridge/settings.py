import json
import os

import bridge.state as state
from bridge.paths import app_dir

TUNING_KEYS = (
    "HEAD_GAIN",
    "EYE_REST",
    "EYE_GAZE",
    "MOUTH_GAIN",
    "SMILE_REST",
    "BROW_GAIN",
    "INVERT_YAW",
    "INVERT_PITCH",
    "INVERT_ROLL",
)
BOOL_KEYS = ("INVERT_YAW", "INVERT_PITCH", "INVERT_ROLL")

PRESETS = {
    "vts": {
        "title": "VTube Studio",
        "waiting": "Waiting for VTube Studio",
        "SMOOTH_FACE": 0.85,
        "SMOOTH_OTHER": 0.7,
        "TICK": 0.016,
        "HEAD_GAIN": 0.4,
        "EYE_REST": 0.5,
        "EYE_GAZE": 1.0,
        "MOUTH_GAIN": 1.0,
        "SMILE_REST": 0.5,
        "BROW_GAIN": 1.0,
        "INVERT_YAW": False,
        "INVERT_PITCH": False,
        "INVERT_ROLL": False,
    },
    "ifm": {
        "title": "iFacialMocap",
        "waiting": "Waiting for iFacialMocap",
        "SMOOTH_FACE": 1.0,
        "SMOOTH_OTHER": 0.85,
        "TICK": 0.016,
        "HEAD_GAIN": 1.0,
        "EYE_REST": 0.9,
        "EYE_GAZE": 1.6,
        "MOUTH_GAIN": 1.8,
        "SMILE_REST": 0.5,
        "BROW_GAIN": 0.9,
        "INVERT_YAW": True,
        "INVERT_PITCH": True,
        "INVERT_ROLL": False,
    },
}

PATH = None


def settings_path():
    return PATH or os.path.join(app_dir(), "bridge_settings.json")


def default_tuning(dest):
    preset = PRESETS[dest]
    return {key: preset[key] for key in TUNING_KEYS}


def snapshot():
    return {key: getattr(state, key) for key in TUNING_KEYS}


def apply_tuning(data):
    base = default_tuning(state.destination)
    if isinstance(data, dict):
        for key in TUNING_KEYS:
            if key in data:
                base[key] = data[key]
    for key in TUNING_KEYS:
        value = base[key]
        if key in BOOL_KEYS:
            value = bool(value)
        else:
            value = float(value)
        setattr(state, key, value)


def apply_mode_constants():
    preset = PRESETS[state.destination]
    state.SMOOTH_FACE = preset["SMOOTH_FACE"]
    state.SMOOTH_OTHER = preset["SMOOTH_OTHER"]
    state.TICK = preset["TICK"]


def ensure_loaded():
    if not state.loaded:
        load()


def load():
    state.loaded = True
    state.destination = "vts"
    state.ifm_host = "127.0.0.1"
    state.ifm_port = 49983
    state.tuning = {dest: default_tuning(dest) for dest in PRESETS}
    path = settings_path()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            data = {}
    dest = data.get("destination")
    if dest in PRESETS:
        state.destination = dest
    host = data.get("ifm_host")
    if isinstance(host, str) and host.strip():
        state.ifm_host = host.strip()
    port = data.get("ifm_port")
    if isinstance(port, int) and 1 <= port <= 65535:
        state.ifm_port = port
    saved = data.get("tuning") if isinstance(data.get("tuning"), dict) else {}
    for name in PRESETS:
        merged = default_tuning(name)
        raw = saved.get(name)
        if isinstance(raw, dict):
            for key in TUNING_KEYS:
                if key in raw:
                    merged[key] = raw[key]
        state.tuning[name] = merged
    apply_mode_constants()
    apply_tuning(state.tuning[state.destination])
    if str(state.status.get("output", "")).startswith("Waiting"):
        state.status["output"] = PRESETS[state.destination]["waiting"]


def save():
    ensure_loaded()
    state.tuning[state.destination] = snapshot()
    folder = os.path.dirname(settings_path())
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {
        "destination": state.destination,
        "ifm_host": state.ifm_host,
        "ifm_port": int(state.ifm_port),
        "tuning": state.tuning,
    }
    with open(settings_path(), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def set_destination(dest):
    if dest not in PRESETS:
        raise ValueError(dest)
    ensure_loaded()
    if dest == state.destination:
        return
    state.tuning[state.destination] = snapshot()
    state.destination = dest
    state.blink_seen["EyeOpenLeft"] = None
    state.blink_seen["EyeOpenRight"] = None
    state.blink_hold["EyeOpenLeft"] = 0
    state.blink_hold["EyeOpenRight"] = 0
    apply_mode_constants()
    apply_tuning(state.tuning[dest])
    if str(state.status.get("output", "")).startswith("Waiting") or state.status.get("output") == "Connected":
        state.status["output"] = PRESETS[dest]["waiting"]
    save()


def read_endpoint(host, port):
    host = (host or "").strip()
    if host:
        state.ifm_host = host
    try:
        number = int(str(port).strip())
    except (TypeError, ValueError):
        return
    if 1 <= number <= 65535:
        state.ifm_port = number
