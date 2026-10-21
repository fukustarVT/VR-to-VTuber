import math

import bridge.state as state
from bridge.face import clamp, g
from bridge.openxr_head import quat_to_matrix, read_pose


def recenter():
    state.head_neutral = None
    state.head_neutral_pos = None
    state.status["detail"] = "Look straight ahead. That pose is the new neck center."
    print("Neck center cleared. Look forward.", flush=True)


def poll_head():
    rot = None
    pos = None
    source = None

    if state.head_error != "missing":
        try:
            import openvr
            if state.vr_system is None:
                openvr.init(openvr.VRApplication_Background)
                state.vr_system = openvr.VRSystem()
            poses = state.vr_system.getDeviceToAbsoluteTrackingPose(
                openvr.TrackingUniverseStanding, 0, openvr.k_unMaxTrackedDeviceCount
            )
            pose = poses[openvr.k_unTrackedDeviceIndex_Hmd]
            if pose.bPoseIsValid:
                m = pose.mDeviceToAbsoluteTracking
                rot = tuple(tuple(m[r][c] for c in range(3)) for r in range(3))
                pos = (m[0][3], m[1][3], m[2][3])
                source = "SteamVR"
        except ImportError:
            if state.head_error is None:
                state.head_error = "missing"
                print("OpenVR not installed. OpenXR layer still works.", flush=True)
        except Exception as exc:
            state.vr_system = None
            try:
                import openvr
                openvr.shutdown()
            except Exception:
                pass
            if state.head_error is None:
                state.head_error = str(exc)
                print(f"SteamVR pose unavailable ({exc}). Trying OpenXR.", flush=True)

    if rot is None:
        try:
            posed = read_pose()
            if posed is not None:
                qx, qy, qz, qw, px, py, pz = posed
                rot = quat_to_matrix(qx, qy, qz, qw)
                pos = (px, py, pz)
                source = "OpenXR"
        except Exception:
            pass

    if rot is None:
        state.status["headset"] = "Waiting for tracking"
        state.status["source"] = ""
        return

    state.status["headset"] = "Connected"
    state.status["source"] = source
    if state.head_neutral is None:
        state.head_neutral = rot
        state.head_neutral_pos = pos
        return
    rel = _mul(_transpose(state.head_neutral), rot)
    yaw, pitch, roll = _euler(rel)
    if state.INVERT_YAW:
        yaw = -yaw
    if state.INVERT_PITCH:
        pitch = -pitch
    if state.INVERT_ROLL:
        roll = -roll
    flex = g("NeckFlexRight") - g("NeckFlexLeft")
    state.outputs["FaceAngleX"] = clamp((yaw + flex * 8.0) * state.HEAD_GAIN, -30, 30)
    state.outputs["FaceAngleY"] = clamp(pitch * state.HEAD_GAIN, -30, 30)
    state.outputs["FaceAngleZ"] = clamp(roll * state.HEAD_GAIN, -30, 30)
    dx = (pos[0] - state.head_neutral_pos[0]) / 0.30
    dy = (pos[1] - state.head_neutral_pos[1]) / 0.22
    dz = (pos[2] - state.head_neutral_pos[2]) / 0.30
    state.outputs["FacePositionX"] = clamp(dx, -1, 1)
    state.outputs["FacePositionY"] = clamp(dy, -1, 1)
    state.outputs["FacePositionZ"] = clamp(-dz, -1, 1)


def _transpose(a):
    return tuple(tuple(a[c][r] for c in range(3)) for r in range(3))


def _mul(a, b):
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
        for i in range(3)
    )


def _euler(m):
    yaw = math.degrees(math.atan2(m[0][2], m[2][2]))
    pitch = math.degrees(math.atan2(-m[1][2], math.sqrt(m[0][2] ** 2 + m[2][2] ** 2)))
    roll = math.degrees(math.atan2(m[1][0], m[1][1]))
    return yaw, pitch, roll
