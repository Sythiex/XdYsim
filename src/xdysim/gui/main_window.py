"""Top-level application window for the XdYsim desktop app."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from xdysim.gui.combat_simulator_tab import CombatSimulatorTab
from xdysim.gui.icons import app_icon
from xdysim.gui.opposed_rolls_tab import OpposedRollsTab
from xdysim.gui.static_checks_tab import StaticChecksTab

DEFAULT_WINDOW_WIDTH = 1680
DEFAULT_WINDOW_HEIGHT = 1020
MIN_WINDOW_WIDTH = 1320
MIN_WINDOW_HEIGHT = 900


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("XdYsim")
        self.setWindowIcon(app_icon())
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        self.tabs = QTabWidget()
        self.tabs.addTab(CombatSimulatorTab(), "Combat Simulator")
        self.tabs.addTab(StaticChecksTab(), "Static Checks")
        self.tabs.addTab(OpposedRollsTab(), "Opposed Rolls")
        self.setCentralWidget(self.tabs)
