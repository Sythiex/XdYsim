from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from xdysim.gui.static_checks_tab import StaticChecksTab


def _application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        return QApplication([])
    if not isinstance(app, QApplication):
        msg = "Tests require a QApplication instance"
        raise RuntimeError(msg)
    return app


def test_static_checks_tab_shows_result_lte_dc_row() -> None:
    _application()
    tab = StaticChecksTab()

    try:
        tab.rank_combo.setCurrentIndex(1)
        tab.dc_spin.setValue(4)

        labels = {label.text() for label in tab.findChildren(QLabel)}
        assert "Result <= DC" in labels
        assert "Result >= DC" not in labels
        assert tab.lte_label.text() == "66.6667% (2/3)"
    finally:
        tab.close()
