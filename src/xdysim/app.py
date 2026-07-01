"""Application entrypoints for launching the XdYsim desktop app."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from xdysim.gui.icons import app_icon
from xdysim.gui.main_window import MainWindow

APP_NAME = "XdYsim"
APP_ID = "Sythiex.XdYsim.XdYsim"


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return

    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Return the shared Qt application instance, creating it when needed."""
    _set_windows_app_id()
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    if not isinstance(app, QApplication):
        msg = "XdYsim requires a QApplication instance"
        raise RuntimeError(msg)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    return app


def main() -> int:
    """Launch the desktop application."""
    app = create_application()
    window = MainWindow()
    window.show()
    return app.exec()
