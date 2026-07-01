"""Shared Edge/Hindrance spin box."""

from __future__ import annotations

from PySide6.QtWidgets import QSpinBox


class EdgeHindranceSpinBox(QSpinBox):
    def textFromValue(self, value: int) -> str:  # noqa: N802
        if value > 0:
            return f"+{value} Edge"
        if value < 0:
            return f"{value} Hindrance"
        return "0"
