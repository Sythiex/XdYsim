"""Opposed-roll analysis tab."""

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

from xdysim.engine import all_dice_pools, opposed_metric_matrices, opposed_roll
from xdysim.engine.models import SkillRank
from xdysim.gui.edge_hindrance_spin_box import EdgeHindranceSpinBox


def _format_probability(probability: Fraction) -> str:
    return f"{float(probability):.4%} ({probability.numerator}/{probability.denominator})"


class OpposedRollsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.attacker_combo = QComboBox()
        self.defender_combo = QComboBox()
        for pool in all_dice_pools():
            label = f"{pool.label} [{pool.full_label}]"
            self.attacker_combo.addItem(label, int(pool.rank))
            self.defender_combo.addItem(label, int(pool.rank))

        self.defender_combo.setCurrentIndex(1)

        self.attacker_edge_hindrance_spin = EdgeHindranceSpinBox()
        self.attacker_edge_hindrance_spin.setRange(-10, 10)
        self.attacker_edge_hindrance_spin.setValue(0)

        self.attacker_circumstance_spin = QSpinBox()
        self.attacker_circumstance_spin.setRange(-40, 40)
        self.attacker_circumstance_spin.setValue(0)

        self.defender_edge_hindrance_spin = EdgeHindranceSpinBox()
        self.defender_edge_hindrance_spin.setRange(-10, 10)
        self.defender_edge_hindrance_spin.setValue(0)

        self.defender_circumstance_spin = QSpinBox()
        self.defender_circumstance_spin.setRange(-40, 40)
        self.defender_circumstance_spin.setValue(0)

        controls_group = QGroupBox("Opposed Check Setup")
        controls_layout = QFormLayout()
        controls_layout.addRow("Attacker", self.attacker_combo)
        controls_layout.addRow("Attacker Edge / Hindrance", self.attacker_edge_hindrance_spin)
        controls_layout.addRow("Attacker Circumstance", self.attacker_circumstance_spin)
        controls_layout.addRow("Defender", self.defender_combo)
        controls_layout.addRow("Defender Edge / Hindrance", self.defender_edge_hindrance_spin)
        controls_layout.addRow("Defender Circumstance", self.defender_circumstance_spin)
        controls_group.setLayout(controls_layout)

        self.win_label = QLabel()
        self.lte_label = QLabel()
        self.margin_label = QLabel()

        summary_group = QGroupBox("Exact Opposed Results")
        summary_layout = QFormLayout()
        summary_layout.addRow("Attacker > Defender", self.win_label)
        summary_layout.addRow("Attacker <= Defender", self.lte_label)
        summary_layout.addRow("Margin: E(max(attacker - defender, 0))", self.margin_label)
        summary_group.setLayout(summary_layout)

        header_layout = QHBoxLayout()
        header_layout.addWidget(controls_group, stretch=1)
        header_layout.addWidget(summary_group, stretch=2)

        self.win_table = QTableWidget()
        self.margin_table = QTableWidget()

        layout = QVBoxLayout()
        layout.addLayout(header_layout)
        layout.addWidget(QLabel("Win probability matrix"))
        layout.addWidget(self.win_table)
        layout.addWidget(QLabel("Expected positive margin matrix"))
        layout.addWidget(self.margin_table)
        self.setLayout(layout)

        self.attacker_combo.currentIndexChanged.connect(self.refresh)
        self.defender_combo.currentIndexChanged.connect(self.refresh)
        self.attacker_edge_hindrance_spin.valueChanged.connect(self.refresh)
        self.attacker_circumstance_spin.valueChanged.connect(self.refresh)
        self.defender_edge_hindrance_spin.valueChanged.connect(self.refresh)
        self.defender_circumstance_spin.valueChanged.connect(self.refresh)
        self.refresh()

    def _selected_attacker(self) -> SkillRank:
        return SkillRank(int(self.attacker_combo.currentData()))

    def _selected_defender(self) -> SkillRank:
        return SkillRank(int(self.defender_combo.currentData()))

    def _populate_matrix_tables(
        self,
        attacker_circumstance: int,
        defender_circumstance: int,
        attacker_edge_hindrance: int,
        defender_edge_hindrance: int,
    ) -> None:
        pools, win_matrix, margin_matrix = opposed_metric_matrices(
            attacker_circumstance=attacker_circumstance,
            defender_circumstance=defender_circumstance,
            attacker_edge_hindrance=attacker_edge_hindrance,
            defender_edge_hindrance=defender_edge_hindrance,
        )
        labels = [pool.label for pool in pools]

        for table in (self.win_table, self.margin_table):
            table.setRowCount(len(labels))
            table.setColumnCount(len(labels))
            table.setVerticalHeaderLabels(labels)
            table.setHorizontalHeaderLabels(labels)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        for row_index, _attacker_label in enumerate(labels):
            for column_index, _defender_label in enumerate(labels):
                win_item = QTableWidgetItem(f"{win_matrix[row_index, column_index]:.4%}")
                margin_item = QTableWidgetItem(f"{margin_matrix[row_index, column_index]:.6f}")
                for item in (win_item, margin_item):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.win_table.setItem(row_index, column_index, win_item)
                self.margin_table.setItem(row_index, column_index, margin_item)

        self.win_table.setToolTip("Rows are attackers, columns are defenders.")
        self.margin_table.setToolTip("Rows are attackers, columns are defenders.")
        self.win_table.resizeColumnsToContents()
        self.margin_table.resizeColumnsToContents()

    def refresh(self) -> None:
        attacker_circumstance = self.attacker_circumstance_spin.value()
        defender_circumstance = self.defender_circumstance_spin.value()
        attacker_edge_hindrance = self.attacker_edge_hindrance_spin.value()
        defender_edge_hindrance = self.defender_edge_hindrance_spin.value()
        summary = opposed_roll(
            self._selected_attacker(),
            self._selected_defender(),
            attacker_circumstance=attacker_circumstance,
            defender_circumstance=defender_circumstance,
            attacker_edge_hindrance=attacker_edge_hindrance,
            defender_edge_hindrance=defender_edge_hindrance,
        )
        self.win_label.setText(_format_probability(summary.probability_attacker_win))
        self.lte_label.setText(_format_probability(summary.probability_attacker_lte))
        self.margin_label.setText(f"{float(summary.expected_positive_margin):.6f}")
        self._populate_matrix_tables(
            attacker_circumstance,
            defender_circumstance,
            attacker_edge_hindrance,
            defender_edge_hindrance,
        )
