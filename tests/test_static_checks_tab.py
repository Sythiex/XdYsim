from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFormLayout, QFrame, QLabel

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


def _chart_values(tab: StaticChecksTab) -> list[float]:
    bar_set = tab.distribution_chart.bar_set
    return [bar_set.at(index) for index in range(bar_set.count())]


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


def test_static_checks_tab_chart_shows_default_distribution() -> None:
    _application()
    tab = StaticChecksTab()

    try:
        assert tab.distribution_chart.chart().title() == "Exact Result Distribution"
        assert tab.distribution_chart.x_axis.titleText() == "Result"
        assert tab.distribution_chart.x_axis.categories() == ["1", "2", "3", "4"]
        assert tab.distribution_chart.y_axis.titleText() == "Probability"
        assert tab.distribution_chart.y_axis.min() == 0.0
        assert tab.distribution_chart.y_axis.tickCount() - 1 >= 3
        assert _chart_values(tab) == pytest.approx([25.0, 25.0, 25.0, 25.0])
        assert not tab.distribution_chart.chart().legend().isVisible()
    finally:
        tab.close()


def test_static_checks_tab_chart_uses_active_palette() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        palette = tab.distribution_chart.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Mid, QColor("#5F6368"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#8AB4F8"))
        tab.distribution_chart.setPalette(palette)
        app.processEvents()

        assert not tab.distribution_chart.chart().isBackgroundVisible()
        assert tab.distribution_chart.backgroundBrush().color() == QColor("#202124")
        assert tab.distribution_chart.chart().titleBrush().color() == QColor("#F1F3F4")
        assert tab.distribution_chart.x_axis.labelsBrush().color() == QColor("#F1F3F4")
        assert tab.distribution_chart.y_axis.labelsBrush().color() == QColor("#F1F3F4")
        assert tab.distribution_chart.x_axis.linePen().color() == QColor("#5F6368")
        grid_color = tab.distribution_chart.x_axis.gridLinePen().color()
        assert grid_color.name() == "#f1f3f4"
        assert grid_color.alpha() == 72
        assert tab.distribution_chart.bar_set.color() == QColor("#8AB4F8")
    finally:
        tab.close()


def test_static_checks_tab_chart_has_at_least_three_y_axis_subdivisions() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        for rank_index in range(tab.rank_combo.count()):
            tab.rank_combo.setCurrentIndex(rank_index)
            for edge_hindrance in range(-2, 3):
                tab.edge_hindrance_spin.setValue(edge_hindrance)
                app.processEvents()

                assert tab.distribution_chart.y_axis.tickCount() - 1 >= 3
    finally:
        tab.close()


def test_static_checks_tab_chart_shows_probability_tooltip_for_hovered_bar() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        tab.resize(1320, 850)
        tab.show()
        app.processEvents()
        chart = tab.distribution_chart
        plot_area = chart.chart().plotArea()
        first_bar_x = plot_area.left() + plot_area.width() / 8
        first_bar_top = (
            plot_area.bottom()
            - plot_area.height() * (25.0 / chart.y_axis.max())
        )
        first_position = QPoint(
            round(first_bar_x),
            round((first_bar_top + plot_area.bottom()) / 2),
        )
        second_position = first_position + QPoint(8, 20)

        QTest.mouseMove(chart.viewport(), first_position)
        app.processEvents()
        tooltip_label = chart._tooltip_label
        assert tooltip_label.text() == "25.0000%"
        assert tooltip_label.isVisible()
        assert tooltip_label.frameShape() == QFrame.Shape.NoFrame
        assert tooltip_label.margin() == 2
        assert tooltip_label.geometry().bottom() < first_position.y()
        first_tooltip_position = tooltip_label.pos()

        QTest.mouseMove(chart.viewport(), second_position)
        app.processEvents()
        assert tooltip_label.isVisible()
        assert tooltip_label.pos() != first_tooltip_position
        assert tooltip_label.geometry().bottom() < second_position.y()

        QTest.mouseMove(
            chart.viewport(),
            QPoint(round(first_bar_x), round(plot_area.top() + 5)),
        )
        app.processEvents()
        assert tooltip_label.isHidden()
    finally:
        tab.close()


def test_static_checks_tab_chart_starts_at_one_after_positive_circumstance() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        tab.circumstance_spin.setValue(1)
        app.processEvents()

        assert tab.distribution_chart.x_axis.categories() == ["1", "2", "3", "4", "5"]
        assert _chart_values(tab) == pytest.approx([0.0, 25.0, 25.0, 25.0, 25.0])
    finally:
        tab.close()


def test_static_checks_tab_chart_extends_below_one_for_negative_results() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        tab.circumstance_spin.setValue(-2)
        app.processEvents()

        assert tab.distribution_chart.x_axis.categories() == ["-1", "0", "1", "2"]
        values = _chart_values(tab)
        assert values == pytest.approx([25.0, 25.0, 25.0, 25.0])
        assert sum(values) == pytest.approx(100.0)
    finally:
        tab.close()


def test_static_checks_tab_chart_updates_for_edge_and_largest_range() -> None:
    app = _application()
    tab = StaticChecksTab()

    try:
        tab.edge_hindrance_spin.setValue(1)
        tab.circumstance_spin.setValue(1)
        app.processEvents()

        assert tab.distribution_chart.x_axis.categories() == ["1", "2", "3", "4", "5"]
        assert _chart_values(tab) == pytest.approx([0.0, 6.25, 18.75, 31.25, 43.75])

        tab.rank_combo.setCurrentIndex(5)
        tab.circumstance_spin.setValue(40)
        app.processEvents()

        categories = tab.distribution_chart.x_axis.categories()
        values = _chart_values(tab)
        assert len(categories) == 65
        assert categories[0] == "1"
        assert categories[-1] == "65"
        assert values[:40] == pytest.approx([0.0] * 40)
        assert sum(values) == pytest.approx(100.0)
        assert tab.distribution_chart.x_axis.labelsAngle() == -90.0
        assert tab.distribution_chart.y_axis.min() == 0.0
        assert tab.distribution_chart.y_axis.max() >= max(values)
    finally:
        tab.close()


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
