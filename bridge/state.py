import threading

raw = {}
outputs = {}
smooth = {}
blink_hold = {"EyeOpenLeft": 0, "EyeOpenRight": 0}
blink_seen = {"EyeOpenLeft": None, "EyeOpenRight": None}
packets = 0
seen = set()
model_params = {}
vd_map = None
vd_layout = None
vr_system = None
head_neutral = None
head_neutral_pos = None
head_error = None
stop_event = threading.Event()

destination = "vts"
ifm_host = "127.0.0.1"
ifm_port = 49983
vts_port = 8001
tuning = {}
loaded = False

HEAD_GAIN = 0.4
EYE_REST = 0.5
EYE_GAZE = 1.0
MOUTH_GAIN = 1.0
SMILE_REST = 0.5
BROW_GAIN = 1.0
INVERT_YAW = False
INVERT_PITCH = False
INVERT_ROLL = False
SMOOTH_FACE = 0.85
SMOOTH_OTHER = 0.7
TICK = 0.016

status = {
    "output": "Waiting for VTube Studio",
    "tracking": "Waiting for VRCFaceTracking",
    "headset": "Waiting for tracking",
    "source": "",
    "detail": "Press Start, then look straight ahead.",
}


def reset_outputs(ranges):
    global outputs, smooth
    outputs = {name: 0.0 for name in ranges}
    outputs["EyeOpenLeft"] = 1.0
    outputs["EyeOpenRight"] = 1.0
    smooth = dict(outputs)
    blink_hold["EyeOpenLeft"] = 0
    blink_hold["EyeOpenRight"] = 0
    blink_seen["EyeOpenLeft"] = None
    blink_seen["EyeOpenRight"] = None
