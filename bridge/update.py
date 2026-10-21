import json
import urllib.request

VERSION = "1.2"
_LATEST = "https://api.github.com/repos/fukustarVT/VR-to-VTuber/releases/latest"


def version_key(tag):
    parts = []
    for piece in str(tag).strip().lstrip("vV").split("."):
        number = ""
        for ch in piece:
            if not ch.isdigit():
                break
            number += ch
        if not number:
            return None
        parts.append(int(number))
    return tuple(parts) if parts else None


def is_newer(remote, local):
    left = version_key(remote)
    right = version_key(local)
    if left is None or right is None:
        return False
    width = max(len(left), len(right))
    left = left + (0,) * (width - len(left))
    right = right + (0,) * (width - len(right))
    return left > right


def latest_url():
    request = urllib.request.Request(_LATEST, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "VR-to-VTuber",
    })
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode())
    except Exception:
        return None
    tag = data.get("tag_name") or ""
    url = data.get("html_url") or ""
    if not url or not is_newer(tag, VERSION):
        return None
    return url
