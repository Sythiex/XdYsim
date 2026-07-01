from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFormLayout, QLabel

from xdysim.engine import opposed_metric_matrices
from xdysim.gui.opposed_rolls_tab import OpposedRollsTab


def _application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        return QApplication([])
    if not isinstance(app, QApplication):
        msg = "Tests require a QApplication instance"
        raise RuntimeError(msg)
    return app


def _controls_layout(tab: OpposedRollsTab) -> QFormLayout:
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


def test_opposed_rolls_tab_setup_controls_use_expected_order() -> None:
    _application()
    tab = OpposedRollsTab()

    try:
        controls_layout = _controls_layout(tab)
        attacker_label = controls_layout.labelForField(tab.attacker_combo)
        attacker_edge_hindrance_label = controls_layout.labelForField(
            tab.attacker_edge_hindrance_spin
        )
        attacker_circumstance_label = controls_layout.labelForField(
            tab.attacker_circumstance_spin
        )
        defender_label = controls_layout.labelForField(tab.defender_combo)
        defender_edge_hindrance_label = controls_layout.labelForField(
            tab.defender_edge_hindrance_spin
        )
        defender_circumstance_label = controls_layout.labelForField(
            tab.defender_circumstance_spin
        )

        assert isinstance(attacker_label, QLabel)
        assert attacker_label.text() == "Attacker"
        assert isinstance(attacker_edge_hindrance_label, QLabel)
        assert attacker_edge_hindrance_label.text() == "Attacker Edge / Hindrance"
        assert isinstance(attacker_circumstance_label, QLabel)
        assert attacker_circumstance_label.text() == "Attacker Circumstance"
        assert isinstance(defender_label, QLabel)
        assert defender_label.text() == "Defender"
        assert isinstance(defender_edge_hindrance_label, QLabel)
        assert defender_edge_hindrance_label.text() == "Defender Edge / Hindrance"
        assert isinstance(defender_circumstance_label, QLabel)
        assert defender_circumstance_label.text() == "Defender Circumstance"
        assert _field_row(controls_layout, tab.attacker_combo) == 0
        assert _field_row(controls_layout, tab.attacker_edge_hindrance_spin) == 1
        assert _field_row(controls_layout, tab.attacker_circumstance_spin) == 2
        assert _field_row(controls_layout, tab.defender_combo) == 3
        assert _field_row(controls_layout, tab.defender_edge_hindrance_spin) == 4
        assert _field_row(controls_layout, tab.defender_circumstance_spin) == 5
        assert tab.attacker_edge_hindrance_spin.minimum() == -10
        assert tab.attacker_edge_hindrance_spin.maximum() == 10
        assert tab.attacker_edge_hindrance_spin.value() == 0
        assert tab.attacker_circumstance_spin.minimum() == -40
        assert tab.attacker_circumstance_spin.maximum() == 40
        assert tab.attacker_circumstance_spin.value() == 0
        assert tab.defender_edge_hindrance_spin.minimum() == -10
        assert tab.defender_edge_hindrance_spin.maximum() == 10
        assert tab.defender_edge_hindrance_spin.value() == 0
        assert tab.defender_circumstance_spin.minimum() == -40
        assert tab.defender_circumstance_spin.maximum() == 40
        assert tab.defender_circumstance_spin.value() == 0
    finally:
        tab.close()


def test_opposed_rolls_tab_shows_attacker_lte_defender_row() -> None:
    _application()
    tab = OpposedRollsTab()

    try:
        labels = {label.text() for label in tab.findChildren(QLabel)}
        assert "Attacker <= Defender" in labels
        assert "P(attacker = defender)" not in labels
    finally:
        tab.close()


def test_opposed_rolls_tab_applies_attacker_edge_hindrance_to_summary_and_matrices() -> None:
    app = _application()
    tab = OpposedRollsTab()

    try:
        tab.attacker_combo.setCurrentIndex(1)
        tab.defender_combo.setCurrentIndex(1)
        tab.attacker_edge_hindrance_spin.setValue(1)
        app.processEvents()

        _pools, win_matrix, margin_matrix = opposed_metric_matrices(
            attacker_edge_hindrance=1,
            defender_edge_hindrance=0,
        )
        win_item = tab.win_table.item(1, 1)
        margin_item = tab.margin_table.item(1, 1)

        assert tab.win_label.text() == "54.9479% (211/384)"
        assert tab.lte_label.text() == "45.0521% (173/384)"
        assert tab.margin_label.text() == "1.238426"
        assert win_item is not None
        assert margin_item is not None
        assert win_item.text() == f"{win_matrix[1, 1]:.4%}"
        assert margin_item.text() == f"{margin_matrix[1, 1]:.6f}"
    finally:
        tab.close()


def test_opposed_rolls_tab_applies_attacker_circumstance_to_summary_and_matrices() -> None:
    app = _application()
    tab = OpposedRollsTab()

    try:
        tab.attacker_combo.setCurrentIndex(1)
        tab.defender_combo.setCurrentIndex(1)
        tab.attacker_circumstance_spin.setValue(1)
        app.processEvents()

        _pools, win_matrix, margin_matrix = opposed_metric_matrices(
            attacker_circumstance=1,
            defender_circumstance=0,
        )
        win_item = tab.win_table.item(1, 1)
        margin_item = tab.margin_table.item(1, 1)

        assert tab.win_label.text() == "59.5486% (343/576)"
        assert tab.lte_label.text() == "40.4514% (233/576)"
        assert tab.margin_label.text() == "1.435764"
        assert win_item is not None
        assert margin_item is not None
        assert win_item.text() == f"{win_matrix[1, 1]:.4%}"
        assert margin_item.text() == f"{margin_matrix[1, 1]:.6f}"
    finally:
        tab.close()
