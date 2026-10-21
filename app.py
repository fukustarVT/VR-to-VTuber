import sys

from bridge.settings import ensure_loaded, set_destination
from bridge.ui import main


if __name__ == "__main__":
    ensure_loaded()
    if "--ifm" in sys.argv:
        set_destination("ifm")
    elif "--vts" in sys.argv:
        set_destination("vts")
    main()
