from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from xdysim.gui.main_window import MainWindow


def _application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
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
