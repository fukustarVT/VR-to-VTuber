import json
import math
import mmap
import struct
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from zeroconf import IPVersion, ServiceInfo, Zeroconf

import bridge.state as state

OSC_IP = "127.0.0.1"
OSC_PORT = 9000
HTTP_PORT = 9002

PARAMS = [
    "v2/EyeLeftX", "v2/EyeLeftY", "v2/EyeRightX", "v2/EyeRightY", "v2/EyeX", "v2/EyeY",
    "v2/EyeLidLeft", "v2/EyeLidRight", "v2/EyeLid",
    "v2/EyeSquintLeft", "v2/EyeSquintRight", "v2/EyeSquint",
    "v2/PupilDilation",
    "v2/BrowPinchLeft", "v2/BrowPinchRight",
    "v2/BrowLowererLeft", "v2/BrowLowererRight",
    "v2/BrowInnerUpLeft", "v2/BrowInnerUpRight", "v2/BrowInnerUp",
    "v2/BrowOuterUpLeft", "v2/BrowOuterUpRight", "v2/BrowOuterUp",
    "v2/BrowDownLeft", "v2/BrowDownRight", "v2/BrowUp",
    "v2/BrowExpressionLeft", "v2/BrowExpressionRight", "v2/BrowExpression",
    "v2/JawOpen", "v2/MouthClosed", "v2/JawX", "v2/JawZ", "v2/JawClench",
    "v2/MouthCornerPullLeft", "v2/MouthCornerPullRight",
    "v2/MouthFrownLeft", "v2/MouthFrownRight",
    "v2/MouthSmileLeft", "v2/MouthSmileRight", "v2/MouthSmile",
    "v2/MouthSadLeft", "v2/MouthSadRight", "v2/MouthSad",
    "v2/MouthX", "v2/MouthUpperX", "v2/MouthLowerX",
    "v2/MouthFunnel", "v2/MouthPucker",
    "v2/MouthStretchLeft", "v2/MouthStretchRight",
    "v2/MouthPressLeft", "v2/MouthPressRight",
    "v2/MouthLowerDownLeft", "v2/MouthLowerDownRight",
    "v2/MouthUpperUpLeft", "v2/MouthUpperUpRight",
    "v2/MouthDimpleLeft", "v2/MouthDimpleRight",
    "v2/TongueOut", "v2/TongueUp", "v2/TongueDown", "v2/TongueLeft", "v2/TongueRight",
    "v2/CheekPuffLeft", "v2/CheekPuffRight", "v2/CheekPuff",
    "v2/CheekSuckLeft", "v2/CheekSuckRight",
    "v2/CheekSquintLeft", "v2/CheekSquintRight",
    "v2/NoseSneerLeft", "v2/NoseSneerRight", "v2/NoseSneer",
    "v2/NeckFlexLeft", "v2/NeckFlexRight",
]


def on_param(addr, *args):
    if not args:
        return
    try:
        value = float(args[0])
    except (TypeError, ValueError):
        return
    state.packets += 1
    name = addr.rsplit("/", 1)[-1]
    if name.endswith("Negative"):
        name = name[: -len("Negative")]
        value = -abs(value)
    elif name.endswith("Positive"):
        name = name[: -len("Positive")]
    if name not in state.seen:
        state.seen.add(name)
        print(f"tracking {name}", flush=True)
    state.raw[name] = value


def leaf(path):
    return {"FULL_PATH": path, "TYPE": "f", "VALUE": [0.0]}


def parameter_tree():
    root = {"FULL_PATH": "/avatar/parameters", "CONTENTS": {}}
    for name in PARAMS:
        node = root["CONTENTS"]
        built = "/avatar/parameters"
        parts = name.split("/")
        for index, part in enumerate(parts):
            built += "/" + part
            if index == len(parts) - 1:
                node[part] = leaf(built)
            else:
                node = node.setdefault(part, {"FULL_PATH": built, "CONTENTS": {}})["CONTENTS"]
    return root


AVATAR = {
    "FULL_PATH": "/avatar",
    "CONTENTS": {
        "change": {"FULL_PATH": "/avatar/change", "TYPE": "s", "VALUE": ["avtr_vts_bridge"]},
        "parameters": parameter_tree(),
    },
}
HOST_INFO = {
    "NAME": "VRChat-Client-VTS",
    "EXTENSIONS": {"ACCESS": True, "CLIPMODE": False, "RANGE": True, "TYPE": True, "VALUE": True},
    "OSC_IP": OSC_IP,
    "OSC_PORT": OSC_PORT,
    "OSC_TRANSPORT": "UDP",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/avatar", "/avatar/parameters"):
            self._send(AVATAR if path != "/" else {"FULL_PATH": "/", "CONTENTS": {"avatar": AVATAR}})
            print(f"VRCFaceTracking read {path}", flush=True)
            return
        if "HOST_INFO" in self.path:
            self._send(HOST_INFO)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt, *args):
        return


def advertise():
    info = ServiceInfo(
        "_oscjson._tcp.local.",
        "VRChat-Client-VTS._oscjson._tcp.local.",
        addresses=[OSC_IP],
        port=HTTP_PORT,
        properties={},
        server="VRChat-Client-VTS.local.",
    )
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    zc.register_service(info)
    print(f"Advertising VRChat-Client-VTS, {len(PARAMS)} face shapes.", flush=True)
    return zc


def open_vd_map():
    if sys.platform != "win32":
        return
    try:
        state.vd_map = mmap.mmap(-1, 4096, tagname="VirtualDesktop.BodyState", access=mmap.ACCESS_READ)
    except (OSError, ValueError, TypeError):
        state.vd_map = None


def read_vd_fallback():
    if state.vd_map is None or state.packets:
        return
    buf = state.vd_map[:]
    if state.vd_layout is None:
        def ok(off):
            vals = struct.unpack_from("<70f", buf, off)
            return sum(-0.25 <= v <= 1.25 and math.isfinite(v) for v in vals) >= 55
        if ok(4):
            state.vd_layout = (4, 296, 292)
        elif ok(2):
            state.vd_layout = (2, 292, 290)
        else:
            return
    weight_off, pose_off, valid_off = state.vd_layout
    weights = struct.unpack_from("<70f", buf, weight_off)
    state.raw["JawOpen"] = weights[24]
    state.raw["EyeLidLeft"] = (1.0 - weights[12]) * 0.75
    state.raw["EyeLidRight"] = (1.0 - weights[13]) * 0.75
    state.raw["MouthCornerPullLeft"] = weights[32]
    state.raw["MouthCornerPullRight"] = weights[33]
    if buf[valid_off] or buf[valid_off + 1]:
        def gaze(off):
            x, y, z, w = struct.unpack_from("<4f", buf, off)
            mag = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
            x, y, z, w = x / mag, y / mag, z / mag, w / mag
            pitch = math.asin(max(-1.0, min(1.0, 2 * (x * z - w * y))))
            yaw = math.atan2(2 * (y * z + w * x), w * w - x * x - y * y + z * z)
            return pitch * 1.6, yaw * 1.6
        state.raw["EyeLeftX"], state.raw["EyeLeftY"] = gaze(pose_off)
        state.raw["EyeRightX"], state.raw["EyeRightY"] = gaze(pose_off + 28)


def make_dispatcher():
    dispatcher = Dispatcher()
    dispatcher.set_default_handler(on_param)
    return dispatcher


async def serve_osc(loop):
    server = AsyncIOOSCUDPServer((OSC_IP, OSC_PORT), make_dispatcher(), loop)
    transport, _ = await server.create_serve_endpoint()
    print(f"Listening on {OSC_IP}:{OSC_PORT}", flush=True)
    return transport


def serve_http():
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((OSC_IP, HTTP_PORT), Handler)
