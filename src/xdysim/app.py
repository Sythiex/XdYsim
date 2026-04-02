"""Application entrypoints for launching the XdYsim desktop app."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from xdysim.gui.main_window import MainWindow

APP_NAME = "XdYsim"


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Return the shared Qt application instance, creating it when needed."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    return app


def main() -> int:
    """Launch the desktop application."""
    app = create_application()
    window = MainWindow()
    window.show()
    return app.exec()
