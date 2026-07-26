"""Qt chart view for exact discrete result distributions."""

from __future__ import annotations

from math import ceil
from typing import override

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QBrush, QMouseEvent, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame, QLabel

from xdysim.engine.models import RollDistribution

_LONG_AXIS_CATEGORY_COUNT = 30
_MINIMUM_Y_AXIS_SUBDIVISIONS = 3
_TOOLTIP_CURSOR_GAP = 12
_TOOLTIP_VIEWPORT_MARGIN = 4


class _ResultDistributionChart(QChartView):
    """Display an exact PMF as one vertical bar per integer result."""

    def __init__(self) -> None:
        chart = QChart()
        super().__init__(chart)

        self.bar_set = QBarSet("Probability")

        self.series = QBarSeries()
        self.series.append(self.bar_set)
        self.series.setLabelsVisible(False)
        self.series.hovered.connect(self._show_probability_tooltip)

        self._last_mouse_position = QPoint()
        self._tooltip_label = QLabel(self.viewport())
        self._tooltip_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
        )
        self._tooltip_label.setAutoFillBackground(True)
        self._tooltip_label.setFrameShape(QFrame.Shape.NoFrame)
        self._tooltip_label.setMargin(2)
        self._tooltip_label.hide()

        self.x_axis = QBarCategoryAxis()
        self.x_axis.setTitleText("Result")

        self.y_axis = QValueAxis()
        self.y_axis.setTitleText("Probability")
        self.y_axis.setLabelFormat("%.0f%%")
        self.y_axis.setMin(0.0)

        chart.setTitle("Exact Result Distribution")
        chart.setBackgroundVisible(False)
        chart.setDropShadowEnabled(False)
        chart.legend().hide()
        chart.addSeries(self.series)
        chart.addAxis(self.x_axis, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(self.y_axis, Qt.AlignmentFlag.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._apply_palette()

    @override
    def changeEvent(self, event: QEvent) -> None:
        """Keep chart colors synchronized with application palette changes."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "bar_set"):
            self._apply_palette()

    def _apply_palette(self) -> None:
        palette = self.palette()
        background = palette.color(QPalette.ColorRole.Window)
        foreground = palette.color(QPalette.ColorRole.WindowText)
        axis_color = palette.color(QPalette.ColorRole.Mid)
        accent = palette.color(QPalette.ColorRole.Highlight)

        self.setBackgroundBrush(QBrush(background))
        self.chart().setTitleBrush(QBrush(foreground))

        axis_pen = QPen(axis_color)
        grid_pen = QPen(foreground)
        grid_color = grid_pen.color()
        grid_color.setAlpha(72)
        grid_pen.setColor(grid_color)

        for axis in (self.x_axis, self.y_axis):
            axis.setLabelsBrush(QBrush(foreground))
            axis.setTitleBrush(QBrush(foreground))
            axis.setLinePen(axis_pen)
            axis.setGridLinePen(grid_pen)

        self.bar_set.setColor(accent)
        self.bar_set.setBorderColor(accent.darker(125))

        tooltip_palette = self._tooltip_label.palette()
        tooltip_palette.setColor(
            QPalette.ColorRole.Window,
            palette.color(QPalette.ColorRole.ToolTipBase),
        )
        tooltip_palette.setColor(
            QPalette.ColorRole.WindowText,
            palette.color(QPalette.ColorRole.ToolTipText),
        )
        self._tooltip_label.setPalette(tooltip_palette)

    def _show_probability_tooltip(
        self,
        hovered: bool,
        index: int,
        bar_set: QBarSet,
    ) -> None:
        if not hovered:
            self._tooltip_label.hide()
            return

        self._tooltip_label.setText(f"{bar_set.at(index):.4f}%")
        self._tooltip_label.adjustSize()
        self._position_tooltip(self._last_mouse_position)
        self._tooltip_label.show()
        self._tooltip_label.raise_()

    def _position_tooltip(self, cursor_position: QPoint) -> None:
        viewport = self.viewport()
        label_width = self._tooltip_label.width()
        label_height = self._tooltip_label.height()

        maximum_x = max(
            _TOOLTIP_VIEWPORT_MARGIN,
            viewport.width() - label_width - _TOOLTIP_VIEWPORT_MARGIN,
        )
        x = min(
            max(
                cursor_position.x() - label_width // 2,
                _TOOLTIP_VIEWPORT_MARGIN,
            ),
            maximum_x,
        )

        y = cursor_position.y() - label_height - _TOOLTIP_CURSOR_GAP
        if y < _TOOLTIP_VIEWPORT_MARGIN:
            y = cursor_position.y() + _TOOLTIP_CURSOR_GAP
        maximum_y = max(
            _TOOLTIP_VIEWPORT_MARGIN,
            viewport.height() - label_height - _TOOLTIP_VIEWPORT_MARGIN,
        )
        y = min(y, maximum_y)
        self._tooltip_label.move(x, y)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._last_mouse_position = event.position().toPoint()
        super().mouseMoveEvent(event)
        if self._tooltip_label.isVisible():
            self._position_tooltip(self._last_mouse_position)

    @override
    def leaveEvent(self, event: QEvent) -> None:
        self._tooltip_label.hide()
        super().leaveEvent(event)

    def set_distribution(self, distribution: RollDistribution) -> None:
        """Replace the plotted values with an exact result distribution."""
        self._tooltip_label.hide()
        minimum_result = min(distribution.pmf)
        maximum_result = max(distribution.pmf)
        axis_minimum = min(1, minimum_result)
        results = range(axis_minimum, maximum_result + 1)
        categories = [str(result) for result in results]
        percentages = [
            float(distribution.probability_of(result)) * 100.0
            for result in range(axis_minimum, maximum_result + 1)
        ]

        if self.bar_set.count():
            self.bar_set.remove(0, self.bar_set.count())
        self.bar_set.append(percentages)

        self.x_axis.clear()
        self.x_axis.append(categories)
        self.x_axis.setLabelsAngle(
            -90 if len(categories) > _LONG_AXIS_CATEGORY_COUNT else 0
        )

        maximum_probability = max(percentages)
        self.y_axis.setRange(0.0, maximum_probability * 1.1)
        self.y_axis.applyNiceNumbers()

        subdivision_count = self.y_axis.tickCount() - 1
        if subdivision_count < _MINIMUM_Y_AXIS_SUBDIVISIONS:
            subdivision_multiplier = ceil(
                _MINIMUM_Y_AXIS_SUBDIVISIONS / subdivision_count
            )
            self.y_axis.setTickCount(
                subdivision_count * subdivision_multiplier + 1
            )
