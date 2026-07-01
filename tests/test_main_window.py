from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from xdysim.app import APP_NAME, create_application
from xdysim.gui.icons import app_icon
from xdysim.gui.main_window import MainWindow


def _application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        return QApplication([])
    if not isinstance(app, QApplication):
        msg = "Tests require a QApplication instance"
        raise RuntimeError(msg)
    return app


def test_main_window_exposes_expected_tabs() -> None:
    _application()
    window = MainWindow()

    try:
        assert window.tabs.count() == 3
        assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == [
            "Combat Simulator",
            "Static Checks",
            "Opposed Rolls",
        ]
    finally:
        window.close()


def test_application_uses_bundled_icon() -> None:
    app = create_application([])

    assert app.applicationName() == APP_NAME
    assert not app_icon().isNull()
    assert not app.windowIcon().isNull()


def test_main_window_uses_bundled_icon() -> None:
    _application()
    window = MainWindow()

    try:
        assert not window.windowIcon().isNull()
    finally:
        window.close()
