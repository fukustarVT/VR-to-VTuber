import asyncio
import json
import os
import time

import bridge.state as state
from bridge.face import RANGES, clamp, compose, smooth_outputs
from bridge.paths import app_dir

PLUGIN_NAME = "VR to VTuber"
PLUGIN_DEV = "local"
TOKEN_PATH = os.path.join(app_dir(), "vts_token.json")

ALIASES = {
    "paramanglex": "FaceAngleX", "paramangley": "FaceAngleY", "paramanglez": "FaceAngleZ",
    "parambodyanglex": "FaceAngleX", "parambodyangley": "FaceAngleY", "parambodyanglez": "FaceAngleZ",
    "parammouthopeny": "MouthOpen", "parammouthform": "MouthSmile",
    "mouthopeny": "MouthOpen", "voicevolumeplusmouthopen": "MouthOpen",
    "parammouthx": "MouthX",
    "parameyeballx": "EyeLeftX", "parameyebally": "EyeLeftY",
    "parameyeopenl": "EyeOpenLeft", "parameyeopenr": "EyeOpenRight",
    "parambrowly": "BrowLeftY", "parambrowry": "BrowRightY",
    "paramcheek": "CheekPuff",
}

_warned = False


def map_range(value, src_lo, src_hi, dst_lo, dst_hi):
    if dst_lo is None or dst_hi is None or dst_lo == dst_hi:
        dst_lo, dst_hi = src_lo, src_hi
    if src_hi == src_lo:
        return dst_lo
    t = clamp((value - src_lo) / (src_hi - src_lo), 0.0, 1.0)
    return dst_lo + t * (dst_hi - dst_lo)


def source_for(name):
    if name in RANGES:
        return name
    key = "".join(ch for ch in name.lower() if ch.isalnum())
    if key in ALIASES:
        return ALIASES[key]
    if "mouthopen" in key or key.endswith("openy"):
        return "MouthOpen"
    if "mouthform" in key or "mouthsmile" in key:
        return "MouthSmile"
    return None


def parameter_payload():
    payload = []
    items = list(state.model_params.items())
    if not items:
        items = [(name, {"min": lo, "max": hi}) for name, (lo, hi) in RANGES.items()]
    seen_ids = set()
    for name, info in items:
        source = source_for(name)
        if source not in RANGES:
            continue
        lo, hi = RANGES[source]
        payload.append({
            "id": name,
            "weight": 1,
            "value": map_range(state.smooth[source], lo, hi, info.get("min"), info.get("max")),
        })
        seen_ids.add(name)
    for name, (lo, hi) in RANGES.items():
        if name in seen_ids:
            continue
        info = state.model_params.get(name, {})
        payload.append({
            "id": name,
            "weight": 1,
            "value": map_range(state.smooth[name], lo, hi, info.get("min"), info.get("max")),
        })
    return payload


def _envelope(message_type, data, request_id):
    return json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": request_id,
        "messageType": message_type,
        "data": data,
    })


def _take_params(message):
    data = message.get("data") or {}
    found = {}
    for entry in data.get("defaultParameters", []) + data.get("customParameters", []):
        name = entry.get("name")
        if name:
            found[name] = entry
    if not found:
        return
    changed = set(found) != set(state.model_params)
    state.model_params = found
    if changed:
        print(f"Model inputs: {len(found)}", flush=True)


async def _read_api(ws):
    try:
        async for raw in ws:
            if state.stop_event.is_set() or state.destination != "vts":
                return
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if message.get("messageType") == "InputParameterListResponse":
                _take_params(message)
    except Exception:
        return


async def session():
    global _warned
    from bridge.osc import read_vd_fallback

    try:
        import websockets
    except ImportError:
        if not _warned:
            _warned = True
            print("VTube Studio output needs websockets. Run: pip install websockets", flush=True)
        state.status["output"] = "Waiting for VTube Studio"
        while not state.stop_event.is_set() and state.destination == "vts":
            await asyncio.sleep(1)
        return

    url = f"ws://127.0.0.1:{int(state.vts_port)}"
    token = None
    if os.path.exists(TOKEN_PATH):
        try:
            token = json.load(open(TOKEN_PATH, encoding="utf-8")).get("token")
        except (OSError, json.JSONDecodeError):
            token = None

    while not state.stop_event.is_set() and state.destination == "vts":
        reader = None
        try:
            async with websockets.connect(url) as ws:
                async def call(message_type, data, request_id):
                    await ws.send(_envelope(message_type, data, request_id))
                    return json.loads(await ws.recv())

                if not token:
                    resp = await call("AuthenticationTokenRequest", {
                        "pluginName": PLUGIN_NAME,
                        "pluginDeveloper": PLUGIN_DEV,
                    }, "token")
                    token = resp["data"]["authenticationToken"]
                    json.dump({"token": token}, open(TOKEN_PATH, "w", encoding="utf-8"))
                    print("Approved in VTube Studio. Token saved.", flush=True)

                auth = await call("AuthenticationRequest", {
                    "pluginName": PLUGIN_NAME,
                    "pluginDeveloper": PLUGIN_DEV,
                    "authenticationToken": token,
                }, "auth")
                if not auth.get("data", {}).get("authenticated"):
                    token = None
                    if os.path.exists(TOKEN_PATH):
                        os.remove(TOKEN_PATH)
                    print("Token rejected. Allow the popup.", flush=True)
                    state.status["output"] = "Waiting for VTube Studio"
                    state.status["detail"] = "Allow the popup in VTube Studio."
                    await asyncio.sleep(2)
                    continue

                print("Connected to VTube Studio.", flush=True)
                state.status["output"] = "Connected"
                reader = asyncio.create_task(_read_api(ws))
                period = 1.0 / 60.0
                next_tick = time.monotonic()
                next_params = 0.0
                while not state.stop_event.is_set() and state.destination == "vts":
                    if reader.done():
                        break
                    now = time.monotonic()
                    if now >= next_params:
                        next_params = now + 5
                        await ws.send(_envelope("InputParameterListRequest", {}, "list"))
                    read_vd_fallback()
                    compose()
                    smooth_outputs()
                    values = parameter_payload()
                    if values:
                        await ws.send(_envelope("InjectParameterDataRequest", {
                            "faceFound": True,
                            "mode": "set",
                            "parameterValues": values,
                        }, "inject"))
                    next_tick += period
                    now = time.monotonic()
                    if next_tick < now:
                        next_tick = now
                    else:
                        await asyncio.sleep(next_tick - now)
        except Exception as exc:
            if state.stop_event.is_set() or state.destination != "vts":
                return
            print(f"VTube Studio not ready ({exc}). Retrying.", flush=True)
            state.status["output"] = "Waiting for VTube Studio"
            await asyncio.sleep(2)
        finally:
            if reader is not None:
                reader.cancel()
                try:
                    await reader
                except (asyncio.CancelledError, Exception):
                    pass
