"""GUI icon resources."""

from __future__ import annotations

from importlib.resources import files

from PySide6.QtGui import QIcon

APP_ICON_FILE = "xdysim.ico"


def app_icon() -> QIcon:
    """Return the bundled application icon."""
    icon_path = files("xdysim.assets").joinpath(APP_ICON_FILE)
    return QIcon(str(icon_path))
