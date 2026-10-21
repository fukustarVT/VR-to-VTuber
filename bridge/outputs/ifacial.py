import asyncio
import socket
import time

import bridge.state as state
from bridge.face import clamp


def packet():
    s = state.smooth
    blink_l = 1.0 - s["EyeOpenLeft"]
    blink_r = 1.0 - s["EyeOpenRight"]
    smile = clamp((s["MouthSmile"] - 0.5) * 2.0, -1.0, 1.0)
    brow_l = s["BrowLeftY"]
    brow_r = s["BrowRightY"]
    lx, ly = s["EyeLeftX"], s["EyeLeftY"]
    rx, ry = s["EyeRightX"], s["EyeRightY"]
    mx = s["MouthX"]

    def pct(value):
        return int(clamp(value, 0.0, 1.0) * 100)

    shapes = {name: 0.0 for name in (
        "browDown_L", "browDown_R", "browInnerUp", "browOuterUp_L", "browOuterUp_R",
        "cheekPuff", "cheekSquint_L", "cheekSquint_R",
        "eyeBlink_L", "eyeBlink_R", "eyeLookDown_L", "eyeLookDown_R",
        "eyeLookIn_L", "eyeLookIn_R", "eyeLookOut_L", "eyeLookOut_R",
        "eyeLookUp_L", "eyeLookUp_R", "eyeSquint_L", "eyeSquint_R", "eyeWide_L", "eyeWide_R",
        "jawForward", "jawLeft", "jawOpen", "jawRight",
        "mouthClose", "mouthDimple_L", "mouthDimple_R", "mouthFrown_L", "mouthFrown_R",
        "mouthFunnel", "mouthLeft", "mouthLowerDown_L", "mouthLowerDown_R",
        "mouthPress_L", "mouthPress_R", "mouthPucker", "mouthRight",
        "mouthRollLower", "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper",
        "mouthSmile_L", "mouthSmile_R", "mouthStretch_L", "mouthStretch_R",
        "mouthUpperUp_L", "mouthUpperUp_R", "noseSneer_L", "noseSneer_R", "tongueOut",
    )}
    shapes.update({
        "eyeBlink_L": blink_l,
        "eyeBlink_R": blink_r,
        "eyeWide_L": max(0.0, s["EyeOpenLeft"] - 0.85) / 0.15,
        "eyeWide_R": max(0.0, s["EyeOpenRight"] - 0.85) / 0.15,
        "eyeLookUp_L": max(ly, 0.0),
        "eyeLookDown_L": max(-ly, 0.0),
        "eyeLookIn_L": max(lx, 0.0),
        "eyeLookOut_L": max(-lx, 0.0),
        "eyeLookUp_R": max(ry, 0.0),
        "eyeLookDown_R": max(-ry, 0.0),
        "eyeLookIn_R": max(-rx, 0.0),
        "eyeLookOut_R": max(rx, 0.0),
        "jawOpen": s["MouthOpen"],
        "mouthLowerDown_L": s["MouthOpen"],
        "mouthLowerDown_R": s["MouthOpen"],
        "mouthSmile_L": max(smile, 0.0),
        "mouthSmile_R": max(smile, 0.0),
        "mouthFrown_L": max(-smile, 0.0),
        "mouthFrown_R": max(-smile, 0.0),
        "mouthLeft": max(-mx, 0.0),
        "mouthRight": max(mx, 0.0),
        "browInnerUp": max((brow_l + brow_r) * 0.5, 0.0),
        "browOuterUp_L": max(brow_l, 0.0),
        "browOuterUp_R": max(brow_r, 0.0),
        "browDown_L": max(-brow_l, 0.0),
        "browDown_R": max(-brow_r, 0.0),
        "cheekPuff": s["CheekPuff"],
        "tongueOut": s["TongueOut"],
        "noseSneer_L": s["FaceAngry"],
        "noseSneer_R": s["FaceAngry"],
    })
    parts = [f"{name}-{pct(value)}" for name, value in shapes.items()]
    pitch, yaw, roll = s["FaceAngleY"], s["FaceAngleX"], s["FaceAngleZ"]
    px = s["FacePositionX"] * 0.05
    py = s["FacePositionY"] * 0.05
    pz = s["FacePositionZ"] * 0.05
    body = "|".join(parts)
    return (
        f"{body}|=head#{pitch:.4f},{yaw:.4f},{roll:.4f},{px:.5f},{py:.5f},{pz:.5f}"
        f"|rightEye#{ry * 18:.4f},{rx * 25:.4f},0|"
        f"|leftEye#{ly * 18:.4f},{lx * 25:.4f},0|"
    ).encode("utf-8")


async def session():
    from bridge.face import compose, smooth_outputs
    from bridge.osc import read_vd_fallback

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Sending iFacialMocap to {state.ifm_host}:{state.ifm_port}", flush=True)
    period = 1.0 / 60.0
    next_tick = time.monotonic()
    try:
        while not state.stop_event.is_set() and state.destination == "ifm":
            read_vd_fallback()
            compose()
            smooth_outputs()
            try:
                sock.sendto(packet(), (state.ifm_host, int(state.ifm_port)))
                state.status["output"] = "Connected"
            except OSError as exc:
                state.status["output"] = "Waiting for iFacialMocap"
                print(f"iFacialMocap send failed ({exc}).", flush=True)
            next_tick += period
            now = time.monotonic()
            if next_tick < now:
                next_tick = now
            else:
                await asyncio.sleep(next_tick - now)
    finally:
        sock.close()
