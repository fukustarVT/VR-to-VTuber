import bridge.state as state

RANGES = {
    "FaceAngleX": (-30, 30), "FaceAngleY": (-30, 30), "FaceAngleZ": (-30, 30),
    "FacePositionX": (-1, 1), "FacePositionY": (-1, 1), "FacePositionZ": (-1, 1),
    "EyeLeftX": (-1, 1), "EyeLeftY": (-1, 1), "EyeRightX": (-1, 1), "EyeRightY": (-1, 1),
    "EyeOpenLeft": (0, 1), "EyeOpenRight": (0, 1),
    "MouthOpen": (0, 1), "VoiceVolumePlusMouthOpen": (0, 1),
    "MouthSmile": (0, 1), "MouthX": (-1, 1),
    "Brows": (-1, 1), "BrowLeftY": (-1, 1), "BrowRightY": (-1, 1),
    "CheekPuff": (0, 1), "TongueOut": (0, 1), "FaceAngry": (0, 1),
}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def g(name, default=0.0):
    return state.raw.get(name, default)


def avg(*names):
    vals = [state.raw[n] for n in names if n in state.raw]
    return sum(vals) / len(vals) if vals else 0.0


def lid_to_open(lid, squint):
    relaxed = state.EYE_REST
    if lid <= 0.75:
        opened = (lid / 0.75) * relaxed
    else:
        opened = relaxed + ((lid - 0.75) / 0.25) * (1.0 - relaxed)
    return clamp(opened - squint * 0.25, 0.0, 1.0)


def deadzone(v, band=0.15):
    v = clamp(v, -1, 1)
    if abs(v) <= band:
        return 0.0
    sign = 1 if v > 0 else -1
    return clamp(sign * (abs(v) - band) / (1 - band), -1, 1)


def compose():
    lx = g("EyeLeftX", g("EyeX"))
    ly = g("EyeLeftY", g("EyeY"))
    rx = g("EyeRightX", g("EyeX", lx))
    ry = g("EyeRightY", g("EyeY", ly))
    state.outputs["EyeLeftX"] = clamp(lx * state.EYE_GAZE, -1, 1)
    state.outputs["EyeLeftY"] = clamp(ly * state.EYE_GAZE, -1, 1)
    state.outputs["EyeRightX"] = clamp(rx * state.EYE_GAZE, -1, 1)
    state.outputs["EyeRightY"] = clamp(ry * state.EYE_GAZE, -1, 1)

    if "EyeLidLeft" in state.raw or "EyeLid" in state.raw:
        state.outputs["EyeOpenLeft"] = lid_to_open(g("EyeLidLeft", g("EyeLid", 0.75)), avg("EyeSquintLeft", "EyeSquint"))
    if "EyeLidRight" in state.raw or "EyeLid" in state.raw:
        state.outputs["EyeOpenRight"] = lid_to_open(g("EyeLidRight", g("EyeLid", 0.75)), avg("EyeSquintRight", "EyeSquint"))

    jaw = clamp(max(g("JawOpen"), avg("MouthLowerDownLeft", "MouthLowerDownRight")) * state.MOUTH_GAIN, 0, 1)
    state.outputs["MouthOpen"] = jaw
    state.outputs["VoiceVolumePlusMouthOpen"] = jaw

    smile = avg("MouthSmile", "MouthSmileLeft", "MouthSmileRight", "MouthCornerPullLeft", "MouthCornerPullRight", "MouthDimpleLeft", "MouthDimpleRight")
    sad = avg("MouthSad", "MouthSadLeft", "MouthSadRight", "MouthFrownLeft", "MouthFrownRight")
    state.outputs["MouthSmile"] = clamp(state.SMILE_REST + (smile * (1.0 - 0.5 * g("MouthPucker")) - sad) * 0.5, 0, 1)
    state.outputs["MouthX"] = clamp(g("MouthX", g("JawX", avg("MouthUpperX", "MouthLowerX"))), -1, 1)

    left_brow = g("BrowExpressionLeft")
    if "BrowExpressionLeft" not in state.raw:
        left_brow = avg("BrowInnerUpLeft", "BrowOuterUpLeft", "BrowUp") - avg("BrowLowererLeft", "BrowDownLeft", "BrowPinchLeft")
    right_brow = g("BrowExpressionRight")
    if "BrowExpressionRight" not in state.raw:
        right_brow = avg("BrowInnerUpRight", "BrowOuterUpRight", "BrowUp") - avg("BrowLowererRight", "BrowDownRight", "BrowPinchRight")
    if "BrowExpression" in state.raw and "BrowExpressionLeft" not in state.raw:
        left_brow = right_brow = g("BrowExpression")
    state.outputs["BrowLeftY"] = clamp(deadzone(left_brow) * state.BROW_GAIN, -1, 1)
    state.outputs["BrowRightY"] = clamp(deadzone(right_brow) * state.BROW_GAIN, -1, 1)
    state.outputs["Brows"] = clamp(deadzone((left_brow + right_brow) / 2) * state.BROW_GAIN, -1, 1)

    puff = g("CheekPuff", avg("CheekPuffLeft", "CheekPuffRight"))
    suck = avg("CheekSuckLeft", "CheekSuckRight")
    state.outputs["CheekPuff"] = clamp(puff - suck, 0, 1)
    state.outputs["TongueOut"] = clamp(max(0.0, g("TongueOut")), 0, 1)
    state.outputs["FaceAngry"] = deadzone(clamp(
        avg("BrowDownLeft", "BrowDownRight", "BrowLowererLeft", "BrowLowererRight", "NoseSneerLeft", "NoseSneerRight", "NoseSneer") * 0.6
        + sad * 0.4,
        0, 1,
    ), 0.12)
    for key in ("EyeOpenLeft", "EyeOpenRight"):
        goal = state.outputs[key]
        if state.blink_seen[key] is None:
            state.blink_seen[key] = goal
        elif state.blink_hold[key] > 0:
            state.blink_hold[key] -= 1
            state.outputs[key] = 0.0
        elif goal < state.blink_seen[key] - 0.12 or goal < 0.18:
            state.outputs[key] = 0.0
            state.blink_hold[key] = 4
        state.blink_seen[key] = goal


def smooth_outputs():
    for key, goal in state.outputs.items():
        if key.startswith("EyeOpen"):
            state.smooth[key] = goal
            continue
        a = state.SMOOTH_FACE if key.startswith("Face") else state.SMOOTH_OTHER
        state.smooth[key] = state.smooth.get(key, 0.0) + (goal - state.smooth.get(key, 0.0)) * a


state.reset_outputs(RANGES)
