import mmap
import struct
import time

NAME = "VRToVTS_HeadPose"
SIZE = 64
FMT = "<QQfffffffII"
STALE_S = 0.25

_mapping = None
_view = None
_last_seq = 0
_last_change = 0.0


def _open():
    global _mapping, _view
    if _view is not None:
        return True
    try:
        _mapping = mmap.mmap(-1, SIZE, tagname=NAME, access=mmap.ACCESS_READ)
        _view = _mapping
        return True
    except (OSError, ValueError, TypeError):
        return False


def layer_status():
    if not _open():
        return "shared memory missing. Build and install the layer, then launch the game."
    try:
        raw = _view[:struct.calcsize(FMT)]
        seq, _ts, *_rest, valid, _pad = struct.unpack(FMT, raw)
    except (ValueError, OSError):
        return "shared memory unreadable"
    if not valid or seq == 0:
        return "layer loaded but no pose yet. Start the OpenXR game."
    return "pose is stale. Is the game still running?"


def read_pose():
    global _last_seq, _last_change
    if not _open():
        return None
    try:
        raw = _view[:struct.calcsize(FMT)]
        seq, _ts, qx, qy, qz, qw, px, py, pz, valid, _pad = struct.unpack(FMT, raw)
    except (ValueError, OSError):
        return None
    if not valid or seq == 0:
        return None
    now = time.monotonic()
    if seq != _last_seq:
        _last_seq = seq
        _last_change = now
    elif now - _last_change > STALE_S:
        return None
    return qx, qy, qz, qw, px, py, pz


def quat_to_matrix(qx, qy, qz, qw):
    xx, yy, zz = qx * qx, qy * qy, qz * qz
    xy, xz, yz = qx * qy, qx * qz, qy * qz
    wx, wy, wz = qw * qx, qw * qy, qw * qz
    return (
        (1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)),
        (2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)),
        (2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)),
    )
