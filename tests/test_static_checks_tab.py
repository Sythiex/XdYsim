from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFormLayout, QLabel

from xdysim.gui.edge_hindrance_spin_box import EdgeHindranceSpinBox
from xdysim.gui.static_checks_tab import StaticChecksTab


def _application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        return QApplication([])
    if not isinstance(app, QApplication):
        msg = "Tests require a QApplication instance"
        raise RuntimeError(msg)
    return app


def _controls_layout(tab: StaticChecksTab) -> QFormLayout:
    top_layout = tab.layout()
    assert top_layout is not None
    header_item = top_layout.itemAt(0)
    assert header_item is not None
    header_layout = header_item.layout()
    assert header_layout is not None
    controls_item = header_layout.itemAt(0)
    assert controls_item is not None
    controls_group = controls_item.widget()
    assert controls_group is not None
    controls_layout = controls_group.layout()
    assert isinstance(controls_layout, QFormLayout)
    return controls_layout


def _field_row(layout: QFormLayout, field: object) -> int:
    for row in range(layout.rowCount()):
        item = layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
        if item is not None and item.widget() is field:
            return row
    msg = "field is not present in form layout"
    raise AssertionError(msg)


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


def test_static_checks_tab_setup_controls_use_expected_order() -> None:
    _application()
    tab = StaticChecksTab()

    try:
        controls_layout = _controls_layout(tab)
        dc_label = controls_layout.labelForField(tab.dc_spin)
        rank_label = controls_layout.labelForField(tab.rank_combo)
        edge_hindrance_label = controls_layout.labelForField(tab.edge_hindrance_spin)
        circumstance_label = controls_layout.labelForField(tab.circumstance_spin)
        dc_row = _field_row(controls_layout, tab.dc_spin)
        rank_row = _field_row(controls_layout, tab.rank_combo)
        edge_hindrance_row = _field_row(controls_layout, tab.edge_hindrance_spin)
        circumstance_row = _field_row(controls_layout, tab.circumstance_spin)

        assert isinstance(dc_label, QLabel)
        assert dc_label.text() == "Static DC"
        assert isinstance(rank_label, QLabel)
        assert rank_label.text() == "Skill Rank"
        assert isinstance(edge_hindrance_label, QLabel)
        assert edge_hindrance_label.text() == "Edge / Hindrance"
        assert isinstance(circumstance_label, QLabel)
        assert circumstance_label.text() == "Circumstance"
        assert dc_row == 0
        assert rank_row == dc_row + 1
        assert edge_hindrance_row == rank_row + 1
        assert circumstance_row == edge_hindrance_row + 1
        assert tab.edge_hindrance_spin.minimum() == -10
        assert tab.edge_hindrance_spin.maximum() == 10
        assert tab.edge_hindrance_spin.value() == 0
        assert tab.circumstance_spin.minimum() == -40
        assert tab.circumstance_spin.maximum() == 40
        assert tab.circumstance_spin.value() == 0
    finally:
        tab.close()


def test_edge_hindrance_spinner_formats_values() -> None:
    spinner = EdgeHindranceSpinBox()

    assert spinner.textFromValue(0) == "0"
    assert spinner.textFromValue(1) == "+1 Edge"
    assert spinner.textFromValue(2) == "+2 Edge"
    assert spinner.textFromValue(-1) == "-1 Hindrance"
    assert spinner.textFromValue(-2) == "-2 Hindrance"


def test_static_checks_tab_applies_circumstance_to_summary_and_distribution() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        tab.rank_combo.setCurrentIndex(1)
        tab.dc_spin.setValue(4)
        tab.circumstance_spin.setValue(1)
        app.processEvents()

        assert tab.gt_label.text() == "62.5000% (5/8)"
        assert tab.eq_label.text() == "20.8333% (5/24)"
        assert tab.lte_label.text() == "37.5000% (3/8)"
        first_result = tab.distribution_table.item(0, 0)
        last_result = tab.distribution_table.item(6, 0)
        assert first_result is not None
        assert last_result is not None
        assert first_result.text() == "2"
        assert last_result.text() == "8"
    finally:
        tab.close()


def test_static_checks_tab_applies_edge_hindrance_to_summary_and_distribution() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        tab.rank_combo.setCurrentIndex(0)
        tab.dc_spin.setValue(2)
        tab.edge_hindrance_spin.setValue(1)
        tab.circumstance_spin.setValue(1)
        app.processEvents()

        assert tab.gt_label.text() == "93.7500% (15/16)"
        assert tab.eq_label.text() == "6.2500% (1/16)"
        assert tab.lte_label.text() == "6.2500% (1/16)"
        first_result = tab.distribution_table.item(0, 0)
        last_result = tab.distribution_table.item(3, 0)
        assert first_result is not None
        assert last_result is not None
        assert first_result.text() == "2"
        assert last_result.text() == "5"
    finally:
        tab.close()
