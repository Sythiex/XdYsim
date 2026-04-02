"""Allow `python -m xdysim` to launch the desktop app."""

from xdysim.app import main

if __name__ == "__main__":
    raise SystemExit(main())
