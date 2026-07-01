"""Static check analysis tab."""

from __future__ import annotations

from fractions import Fraction

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xdysim.engine import all_dice_pools, distribution_for_rank_with_edge, static_check
from xdysim.engine.models import SkillRank
from xdysim.gui.edge_hindrance_spin_box import EdgeHindranceSpinBox


def _format_probability(probability: Fraction) -> str:
    return f"{float(probability):.4%} ({probability.numerator}/{probability.denominator})"


class StaticChecksTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.rank_combo = QComboBox()
        for pool in all_dice_pools():
            self.rank_combo.addItem(f"{pool.label} [{pool.full_label}]", int(pool.rank))

        self.dc_spin = QSpinBox()
        self.dc_spin.setRange(0, 40)
        self.dc_spin.setValue(4)

        self.circumstance_spin = QSpinBox()
        self.circumstance_spin.setRange(-40, 40)
        self.circumstance_spin.setValue(0)

        self.edge_hindrance_spin = EdgeHindranceSpinBox()
        self.edge_hindrance_spin.setRange(-10, 10)
        self.edge_hindrance_spin.setValue(0)

        controls_group = QGroupBox("Check Setup")
        controls_layout = QFormLayout()
        controls_layout.addRow("Static DC", self.dc_spin)
        controls_layout.addRow("Skill Rank", self.rank_combo)
        controls_layout.addRow("Edge / Hindrance", self.edge_hindrance_spin)
        controls_layout.addRow("Circumstance", self.circumstance_spin)
        controls_group.setLayout(controls_layout)

        self.gt_label = QLabel()
        self.eq_label = QLabel()
        self.lte_label = QLabel()

        summary_group = QGroupBox("Exact Probabilities")
        summary_layout = QFormLayout()
        summary_layout.addRow("Result > DC", self.gt_label)
        summary_layout.addRow("Result = DC", self.eq_label)
        summary_layout.addRow("Result <= DC", self.lte_label)
        summary_group.setLayout(summary_layout)

        header_layout = QHBoxLayout()
        header_layout.addWidget(controls_group, stretch=1)
        header_layout.addWidget(summary_group, stretch=2)

        self.distribution_table = QTableWidget(0, 3)
        self.distribution_table.setHorizontalHeaderLabels(["Result", "Exact", "Percent"])
        self.distribution_table.verticalHeader().setVisible(False)
        self.distribution_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.distribution_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        container = QVBoxLayout()
        container.addLayout(header_layout)
        container.addWidget(QLabel("Exact result distribution"))
        container.addWidget(self.distribution_table)
        self.setLayout(container)

        self.rank_combo.currentIndexChanged.connect(self.refresh)
        self.dc_spin.valueChanged.connect(self.refresh)
        self.edge_hindrance_spin.valueChanged.connect(self.refresh)
        self.circumstance_spin.valueChanged.connect(self.refresh)
        self.refresh()

    def _selected_rank(self) -> SkillRank:
        return SkillRank(int(self.rank_combo.currentData()))

    def refresh(self) -> None:
        rank = self._selected_rank()
        circumstance = self.circumstance_spin.value()
        edge_hindrance = self.edge_hindrance_spin.value()
        summary = static_check(
            rank,
            self.dc_spin.value(),
            circumstance=circumstance,
            edge_hindrance=edge_hindrance,
        )
        distribution = distribution_for_rank_with_edge(
            rank,
            edge_hindrance=edge_hindrance,
        ).shifted(circumstance)

        self.gt_label.setText(_format_probability(summary.probability_gt))
        self.eq_label.setText(_format_probability(summary.probability_eq))
        self.lte_label.setText(_format_probability(summary.probability_lte))

        ordered_rows = distribution.ordered_pmf
        self.distribution_table.setRowCount(len(ordered_rows))
        for row_index, (result, probability) in enumerate(ordered_rows):
            result_item = QTableWidgetItem(str(result))
            exact_item = QTableWidgetItem(f"{probability.numerator}/{probability.denominator}")
            percent_item = QTableWidgetItem(f"{float(probability):.4%}")
            for item in (result_item, exact_item, percent_item):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.distribution_table.setItem(row_index, 0, result_item)
            self.distribution_table.setItem(row_index, 1, exact_item)
            self.distribution_table.setItem(row_index, 2, percent_item)

        self.distribution_table.resizeColumnsToContents()
