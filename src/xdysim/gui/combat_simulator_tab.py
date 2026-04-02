"""Combat simulator tab and supporting widgets for configuring team battles."""

from __future__ import annotations

import random
import re
import traceback
import weakref
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QThread, Signal
from PySide6.QtGui import QAction, QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from xdysim.engine import (
    Armor,
    Combatant,
    CombatantReference,
    CombatProfile,
    CombatSimulatorPreset,
    CombatTeam,
    DuelSimulationConfig,
    InjuryTrack,
    PresetCodecError,
    SkillRank,
    analyze_opening_attack,
    app_preset_file_name,
    decode_combat_simulator_preset_share_string,
    default_app_preset_directory,
    encode_combat_simulator_preset_share_string,
    load_combat_simulator_preset_file,
    save_combat_simulator_preset_file,
    simulate_team_battle,
)
from xdysim.engine.combat import TeamBattleSimulationResult
from xdysim.engine.models import all_dice_pools

CARD_MIME_TYPE = "application/x-xdysim-combatant-card"
TRAILING_NUMBER_PATTERN = re.compile(r"^(?P<base>.*?)(?:\s+(?P<number>\d+))?$")
RUN_SIMULATION_PROMPT = "Run a simulation"


def _format_probability(probability: float | Fraction) -> str:
    return f"{float(probability):.4%}"


def _set_centered_item(table: QTableWidget, row: int, column: int, value: str) -> None:
    item = QTableWidgetItem(value)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    table.setItem(row, column, item)


def _base_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return ""
    match = TRAILING_NUMBER_PATTERN.match(cleaned)
    if match is None:
        return cleaned
    base = match.group("base").strip()
    return base or cleaned


def unique_combatant_name(preferred_name: str, taken_names: set[str], fallback_name: str) -> str:
    candidate = preferred_name.strip() or fallback_name
    if candidate not in taken_names:
        return candidate

    root_name = _base_name(candidate) or fallback_name
    used_suffixes = {
        int(match.group("number"))
        for taken_name in taken_names
        if (match := TRAILING_NUMBER_PATTERN.match(taken_name.strip())) is not None
        and match.group("base").strip() == root_name
        and match.group("number") is not None
    }
    if root_name in taken_names:
        used_suffixes.add(1)

    suffix = 2
    while suffix in used_suffixes:
        suffix += 1
    return f"{root_name} {suffix}"


class _TeamBattleSimulationThread(QThread):
    progress_changed = Signal(int, int)
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        team_one: CombatTeam,
        team_two: CombatTeam,
        config: DuelSimulationConfig,
    ) -> None:
        super().__init__()
        self._team_one = team_one
        self._team_two = team_two
        self._config = config

    def _emit_progress(self, completed_trials: int, total_trials: int) -> None:
        self.progress_changed.emit(completed_trials, total_trials)

    def run(self) -> None:
        try:
            result = simulate_team_battle(
                self._team_one,
                self._team_two,
                self._config,
                progress_callback=self._emit_progress,
            )
        except Exception:  # pragma: no cover - exercised via GUI failure handling
            self.failed.emit(traceback.format_exc())
            return

        self.result_ready.emit(result)


@dataclass
class _CardDragState:
    card: _CombatantCard
    source_editor: _CombatantTeamEditor
    source_index: int
    target_editor: _CombatantTeamEditor | None = None
    target_index: int | None = None
    dropped: bool = False


class _DropIndicator(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background-color: #2f7de1; border-radius: 3px;")
        self.hide()


class _ShareStringDialog(QDialog):
    def __init__(self, share_string: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Preset String")
        self.resize(760, 260)

        description = QLabel(
            "Copy this share string to send the current combat simulator preset to someone else."
        )
        description.setWordWrap(True)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setPlainText(share_string)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_button = QPushButton("Copy")
        button_box.addButton(copy_button, QDialogButtonBox.ButtonRole.ActionRole)
        copy_button.clicked.connect(self._copy_text)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(description)
        layout.addWidget(self.text_edit)
        layout.addWidget(button_box)
        self.setLayout(layout)

    def _copy_text(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text_edit.toPlainText())


class _DragHandle(QLabel):
    def __init__(self, card: _CombatantCard) -> None:
        super().__init__("|||")
        self._card = card
        self._drag_start_position = QPoint()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFixedWidth(28)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_position = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._drag_start_position).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._drag_start_position = QPoint()
            self._card.start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start_position = QPoint()
        super().mouseReleaseEvent(event)


class _CombatantCard(QFrame):
    changed = Signal()
    duplicate_requested = Signal(object)
    remove_requested = Signal(object)

    def __init__(self, team_editor: _CombatantTeamEditor) -> None:
        super().__init__()
        self._team_editor = team_editor
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setLineWidth(2)

        self.handle = _DragHandle(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Combatant name")

        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.setFixedWidth(76)
        self.duplicate_button.clicked.connect(lambda: self.duplicate_requested.emit(self))

        self.remove_button = QPushButton("Remove")
        self.remove_button.setFixedWidth(64)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))

        self.attack_rank_combo = QComboBox()
        self.defense_rank_combo = QComboBox()
        self.initiative_rank_combo = QComboBox()
        for pool in all_dice_pools():
            self.attack_rank_combo.addItem(pool.label, int(pool.rank))
            self.defense_rank_combo.addItem(pool.label, int(pool.rank))
            self.initiative_rank_combo.addItem(pool.label, int(pool.rank))
        self.attack_rank_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.defense_rank_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.initiative_rank_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.attack_rank_combo.currentIndexChanged.connect(lambda: self.changed.emit())
        self.defense_rank_combo.currentIndexChanged.connect(lambda: self.changed.emit())
        self.initiative_rank_combo.currentIndexChanged.connect(lambda: self.changed.emit())

        self.armor_spin = QSpinBox()
        self.armor_spin.setRange(0, 99)
        self.armor_spin.valueChanged.connect(lambda: self.changed.emit())

        self.minor_capacity_spin = QSpinBox()
        self.minor_capacity_spin.setRange(0, 99)
        self.minor_capacity_spin.valueChanged.connect(lambda: self.changed.emit())

        self.major_capacity_spin = QSpinBox()
        self.major_capacity_spin.setRange(0, 99)
        self.major_capacity_spin.valueChanged.connect(lambda: self.changed.emit())

        header_layout = QHBoxLayout()
        header_layout.addWidget(self.handle)
        header_layout.addWidget(self.name_edit, stretch=1)
        header_layout.addStretch(1)
        header_layout.addWidget(self.duplicate_button)
        header_layout.addWidget(self.remove_button)

        skill_row = QHBoxLayout()
        skill_row.setContentsMargins(0, 0, 0, 0)
        skill_row.setSpacing(8)
        skill_row.addWidget(QLabel("Attack"))
        skill_row.addWidget(self.attack_rank_combo)
        skill_row.addSpacing(12)
        skill_row.addWidget(QLabel("Defense"))
        skill_row.addWidget(self.defense_rank_combo)
        skill_row.addSpacing(12)
        skill_row.addWidget(QLabel("Initiative"))
        skill_row.addWidget(self.initiative_rank_combo)
        skill_row.addStretch(1)

        track_row = QHBoxLayout()
        track_row.setContentsMargins(0, 0, 0, 0)
        track_row.setSpacing(8)
        track_row.addWidget(QLabel("Armor"))
        track_row.addWidget(self.armor_spin)
        track_row.addSpacing(12)
        track_row.addWidget(QLabel("Minor injuries"))
        track_row.addWidget(self.minor_capacity_spin)
        track_row.addSpacing(12)
        track_row.addWidget(QLabel("Major injuries"))
        track_row.addWidget(self.major_capacity_spin)
        track_row.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(header_layout)
        layout.addLayout(skill_row)
        layout.addLayout(track_row)
        self.setLayout(layout)

    def set_card_label(self, label: str) -> None:
        self.name_edit.setPlaceholderText(label)

    def set_remove_enabled(self, enabled: bool) -> None:
        self.remove_button.setEnabled(enabled)

    def populate_from_combatant(self, combatant: Combatant) -> None:
        self.name_edit.setText(combatant.name)
        self.attack_rank_combo.setCurrentIndex(int(combatant.combat.attack_skill_rank) - 1)
        self.defense_rank_combo.setCurrentIndex(int(combatant.combat.defense_skill_rank) - 1)
        self.initiative_rank_combo.setCurrentIndex(int(combatant.combat.initiative_skill_rank) - 1)
        self.armor_spin.setValue(combatant.armor.rating)
        self.minor_capacity_spin.setValue(combatant.injury_track.minor_capacity)
        self.major_capacity_spin.setValue(combatant.injury_track.major_capacity)

    def build_combatant(self) -> Combatant:
        name = self.name_edit.text().strip() or self.name_edit.placeholderText()
        attack_rank = SkillRank(int(self.attack_rank_combo.currentData()))
        defense_rank = SkillRank(int(self.defense_rank_combo.currentData()))
        initiative_rank = SkillRank(int(self.initiative_rank_combo.currentData()))
        return Combatant(
            name=name,
            combat=CombatProfile(
                attack_skill_rank=attack_rank,
                defense_skill_rank=defense_rank,
                initiative_skill_rank=initiative_rank,
            ),
            armor=Armor(rating=self.armor_spin.value()),
            injury_track=InjuryTrack(
                minor_capacity=self.minor_capacity_spin.value(),
                major_capacity=self.major_capacity_spin.value(),
            ),
        )

    def start_drag(self) -> None:
        self._team_editor.start_drag(self)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]  # noqa: N802
        if event.mimeData().hasFormat(CARD_MIME_TYPE):
            drop_y = self.mapToParent(event.position().toPoint()).y()
            self._team_editor.preview_drop(drop_y)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]  # noqa: N802
        if event.mimeData().hasFormat(CARD_MIME_TYPE):
            drop_y = self.mapToParent(event.position().toPoint()).y()
            self._team_editor.preview_drop(drop_y)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]  # noqa: N802
        if event.mimeData().hasFormat(CARD_MIME_TYPE):
            drop_y = self.mapToParent(event.position().toPoint()).y()
            self._team_editor.drop_card(drop_y)
            event.acceptProposedAction()
        else:
            event.ignore()


class _CombatantCardContainer(QWidget):
    def __init__(self, team_editor: _CombatantTeamEditor) -> None:
        super().__init__()
        self._team_editor = team_editor
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]  # noqa: N802
        if event.mimeData().hasFormat(CARD_MIME_TYPE):
            self._team_editor.preview_drop(event.position().toPoint().y())
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]  # noqa: N802
        if event.mimeData().hasFormat(CARD_MIME_TYPE):
            self._team_editor.preview_drop(event.position().toPoint().y())
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]  # noqa: N802
        if event.mimeData().hasFormat(CARD_MIME_TYPE):
            self._team_editor.drop_card(event.position().toPoint().y())
            event.acceptProposedAction()
        else:
            event.ignore()


class _CombatantTeamEditor(QGroupBox):
    _active_drag_state: _CardDragState | None = None
    _all_editors: weakref.WeakSet[_CombatantTeamEditor] = weakref.WeakSet()
    team_changed = Signal()

    def __init__(
        self,
        title: str,
        name_prefix: str,
        default_attack_rank: SkillRank,
        default_defense_rank: SkillRank,
        default_initiative_rank: SkillRank,
        default_armor: int,
    ) -> None:
        super().__init__(title)
        self._name_prefix = name_prefix
        self._default_attack_rank = default_attack_rank
        self._default_defense_rank = default_defense_rank
        self._default_initiative_rank = default_initiative_rank
        self._default_armor = default_armor
        self._cards: list[_CombatantCard] = []
        self._drop_indicator = _DropIndicator()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(430)
        self.setMinimumHeight(420)
        type(self)._all_editors.add(self)
        self.destroyed.connect(lambda *_: type(self)._all_editors.discard(self))

        self.container = _CombatantCardContainer(self)
        self.cards_layout = QVBoxLayout()
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.container.setLayout(self.cards_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.container)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.add_button = QPushButton("Add Combatant")
        self.add_button.clicked.connect(lambda: self.add_card())

        layout = QVBoxLayout()
        layout.addWidget(self.scroll_area)
        layout.addWidget(self.add_button)
        self.setLayout(layout)

        self.add_card()

    def _default_combatant(self) -> Combatant:
        index = len(self._cards) + 1
        return Combatant(
            name=f"{self._name_prefix} {index}",
            combat=CombatProfile(
                attack_skill_rank=self._default_attack_rank,
                defense_skill_rank=self._default_defense_rank,
                initiative_skill_rank=self._default_initiative_rank,
            ),
            armor=Armor(rating=self._default_armor),
            injury_track=InjuryTrack(minor_capacity=2, major_capacity=2),
        )

    def _refresh_card_labels(self) -> None:
        can_remove = len(self._cards) > 1
        for card in self._cards:
            card.set_card_label(self._fallback_name_for_card(card))
            card.set_remove_enabled(can_remove)

    def _fallback_name_for_card(self, card: _CombatantCard) -> str:
        return f"{self._name_prefix} {self._cards.index(card) + 1}"

    def normalize_card_name(self, card: _CombatantCard) -> None:
        taken_names = {
            other_card.name_edit.text().strip()
            for other_card in self._cards
            if other_card is not card and other_card.name_edit.text().strip()
        }
        normalized_name = unique_combatant_name(
            card.name_edit.text(),
            taken_names,
            self._fallback_name_for_card(card),
        )
        if card.name_edit.text() != normalized_name:
            card.name_edit.setText(normalized_name)

    def _normalize_all_card_names(self) -> None:
        for card in self._cards:
            self.normalize_card_name(card)

    @classmethod
    def _clear_all_drop_indicators(
        cls,
        except_editor: _CombatantTeamEditor | None = None,
    ) -> None:
        for editor in tuple(cls._all_editors):
            if editor is not except_editor:
                try:
                    editor._clear_drop_indicator()
                except RuntimeError:
                    cls._all_editors.discard(editor)

    def _emit_team_changed(self) -> None:
        self.team_changed.emit()

    def _clear_drop_indicator(self) -> None:
        if self.cards_layout.indexOf(self._drop_indicator) != -1:
            self.cards_layout.removeWidget(self._drop_indicator)
        self._drop_indicator.hide()

    def _show_drop_indicator(self, target_index: int) -> None:
        target_index = max(0, min(target_index, len(self._cards)))
        type(self)._clear_all_drop_indicators(except_editor=self)
        if self.cards_layout.indexOf(self._drop_indicator) != -1:
            self.cards_layout.removeWidget(self._drop_indicator)
        self.cards_layout.insertWidget(target_index, self._drop_indicator)
        self._drop_indicator.show()

    def _drop_index_for_position(self, drop_y: int) -> int:
        for index, card in enumerate(self._cards):
            midpoint = card.geometry().top() + (card.height() // 2)
            if drop_y < midpoint:
                return index
        return len(self._cards)

    def _insert_card(self, card: _CombatantCard, index: int) -> None:
        insert_at = max(0, min(index, len(self._cards)))
        card._team_editor = self
        self._cards.insert(insert_at, card)
        self.cards_layout.insertWidget(insert_at, card)
        card.show()
        self._refresh_card_labels()

    def _restore_active_drag(self) -> None:
        drag_state = type(self)._active_drag_state
        if drag_state is None or drag_state.dropped:
            return
        drag_state.source_editor._insert_card(drag_state.card, drag_state.source_index)
        type(self)._clear_all_drop_indicators()

    def _begin_drag(self, card: _CombatantCard) -> None:
        source_index = self._cards.index(card)
        type(self)._active_drag_state = _CardDragState(
            card=card,
            source_editor=self,
            source_index=source_index,
            target_editor=self,
            target_index=source_index,
        )
        self.cards_layout.removeWidget(card)
        self._cards.pop(source_index)
        card.hide()
        self._refresh_card_labels()
        self._show_drop_indicator(source_index)

    def _finalize_card_name(self, card: _CombatantCard) -> None:
        self.normalize_card_name(card)
        self._emit_team_changed()

    def add_card(
        self,
        combatant: Combatant | None = None,
        index: int | None = None,
        *,
        emit_change: bool = True,
    ) -> None:
        card = _CombatantCard(self)
        card.populate_from_combatant(combatant or self._default_combatant())
        card.changed.connect(self._emit_team_changed)
        card.duplicate_requested.connect(self.duplicate_card)
        card.remove_requested.connect(self.remove_card)
        card.name_edit.editingFinished.connect(lambda: self._finalize_card_name(card))

        insert_at = len(self._cards) if index is None else index
        self._cards.insert(insert_at, card)
        self.cards_layout.insertWidget(insert_at, card)
        self._refresh_card_labels()
        self.normalize_card_name(card)
        if emit_change:
            self._emit_team_changed()

    def duplicate_card(self, card: _CombatantCard) -> None:
        source_index = self._cards.index(card)
        self.add_card(combatant=card.build_combatant(), index=source_index + 1)

    def remove_card(self, card: _CombatantCard) -> None:
        if len(self._cards) <= 1:
            return
        self.cards_layout.removeWidget(card)
        self._cards.remove(card)
        card.deleteLater()
        self._refresh_card_labels()
        self._emit_team_changed()

    def start_drag(self, card: _CombatantCard) -> None:
        drag_pixmap = card.grab()
        self._begin_drag(card)
        drag = QDrag(card)
        mime_data = QMimeData()
        mime_data.setData(CARD_MIME_TYPE, b"card")
        drag.setMimeData(mime_data)
        drag.setPixmap(drag_pixmap)
        drag.setHotSpot(QPoint(20, 20))
        drag.exec(Qt.DropAction.MoveAction)
        self._restore_active_drag()
        type(self)._clear_all_drop_indicators()
        type(self)._active_drag_state = None

    def preview_drop(self, drop_y: int) -> None:
        drag_state = type(self)._active_drag_state
        if drag_state is None:
            return

        target_index = self._drop_index_for_position(drop_y)
        drag_state.target_editor = self
        drag_state.target_index = target_index
        self._show_drop_indicator(target_index)

    def drop_card(self, drop_y: int) -> None:
        drag_state = type(self)._active_drag_state
        if drag_state is None:
            return
        self.preview_drop(drop_y)

        target_editor = self
        target_index = drag_state.target_index if drag_state.target_index is not None else 0
        cross_team_move = target_editor is not drag_state.source_editor
        if cross_team_move and not drag_state.source_editor._cards:
            target_editor = drag_state.source_editor
            target_index = drag_state.source_index

        target_editor._insert_card(drag_state.card, target_index)
        target_editor.normalize_card_name(drag_state.card)

        if target_editor is drag_state.source_editor:
            target_editor._emit_team_changed()
        else:
            drag_state.source_editor._refresh_card_labels()
            drag_state.source_editor._emit_team_changed()
            target_editor._emit_team_changed()

        drag_state.dropped = True
        type(self)._clear_all_drop_indicators()
        type(self)._active_drag_state = None

    def combatant_snapshots(self) -> tuple[tuple[str, Combatant], ...]:
        return tuple((str(id(card)), card.build_combatant()) for card in self._cards)

    def load_team(self, team: CombatTeam) -> None:
        while self._cards:
            card = self._cards.pop()
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        for combatant in team.combatants:
            self.add_card(combatant=combatant, emit_change=False)
        self._refresh_card_labels()
        self._normalize_all_card_names()
        self._emit_team_changed()

    def build_team(self) -> CombatTeam:
        self._normalize_all_card_names()
        return CombatTeam(
            name=self.title(),
            combatants=tuple(card.build_combatant() for card in self._cards),
        )


class CombatSimulatorTab(QWidget):
    def __init__(self, preset_directory: Path | None = None) -> None:
        super().__init__()
        self._last_result: TeamBattleSimulationResult | None = None
        self._reference_combatants: dict[str, Combatant] = {}
        self._reference_selection_by_key: dict[str, CombatantReference] = {}
        self._reference_key_by_position: dict[tuple[int, int], str] = {}
        self._simulation_thread: _TeamBattleSimulationThread | None = None
        self._preset_directory = preset_directory or default_app_preset_directory()

        self.menu_bar = QMenuBar()
        self.menu_bar.setNativeMenuBar(False)
        self.menu_bar.setStyleSheet(
            """
            QMenuBar {
                background-color: palette(alternate-base);
                border: 1px solid palette(mid);
                border-radius: 6px;
                padding: 2px 4px;
            }

            QMenuBar::item {
                background-color: palette(button);
                border: 1px solid palette(midlight);
                border-radius: 4px;
                padding: 4px 12px;
                margin: 2px 6px 2px 0px;
            }

            QMenuBar::item:selected {
                background-color: palette(highlight);
                color: palette(highlighted-text);
            }

            QMenu {
                border: 1px solid palette(mid);
            }
            """
        )
        self._build_menu_bar()

        self.team_one_editor = _CombatantTeamEditor(
            title="Team 1",
            name_prefix="Team 1",
            default_attack_rank=SkillRank.ONE,
            default_defense_rank=SkillRank.ONE,
            default_initiative_rank=SkillRank.ONE,
            default_armor=0,
        )
        self.team_two_editor = _CombatantTeamEditor(
            title="Team 2",
            name_prefix="Team 2",
            default_attack_rank=SkillRank.ONE,
            default_defense_rank=SkillRank.ONE,
            default_initiative_rank=SkillRank.ONE,
            default_armor=0,
        )
        self.team_one_editor.team_changed.connect(self._refresh_reference_selectors_from_editors)
        self.team_two_editor.team_changed.connect(self._refresh_reference_selectors_from_editors)

        self.trials_spin = QSpinBox()
        self.trials_spin.setRange(100, 100_000)
        self.trials_spin.setSingleStep(100)
        self.trials_spin.setValue(5_000)

        self.max_rounds_spin = QSpinBox()
        self.max_rounds_spin.setRange(1, 1_000)
        self.max_rounds_spin.setValue(30)

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(-1, 999_999_999)
        self.seed_spin.setSpecialValueText("")
        self.seed_spin.setValue(42)
        self.seed_spin.setAccelerated(True)
        self.seed_randomize_button = QPushButton("Randomize")
        self.seed_randomize_button.clicked.connect(self._randomize_seed)
        self.seed_controls_widget = QWidget()
        self.seed_controls_layout = QHBoxLayout()
        self.seed_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.seed_controls_layout.setSpacing(6)
        self.seed_controls_layout.addWidget(self.seed_spin, stretch=1)
        self.seed_controls_layout.addWidget(self.seed_randomize_button)
        self.seed_controls_widget.setLayout(self.seed_controls_layout)

        self.run_button = QPushButton("Run Simulation")
        self.run_button.clicked.connect(self.run_simulation)
        self.run_button.setFixedHeight(34)
        self.run_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.run_progress_bar = QProgressBar()
        self.run_progress_bar.setRange(0, 100)
        self.run_progress_bar.setValue(0)
        self.run_progress_bar.setTextVisible(True)
        self.run_progress_bar.setFormat("Running simulation... %p%")
        self.run_progress_bar.setFixedHeight(34)
        self.run_progress_bar.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.run_controls_widget = QWidget()
        self.run_controls_widget.setFixedHeight(34)
        self.run_controls_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.run_controls_layout = QStackedLayout()
        self.run_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.run_controls_layout.addWidget(self.run_button)
        self.run_controls_layout.addWidget(self.run_progress_bar)
        self.run_controls_widget.setLayout(self.run_controls_layout)

        simulation_group = QGroupBox("Simulation Setup")
        simulation_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        simulation_group.setMinimumWidth(300)
        simulation_form = QFormLayout()
        simulation_form.addRow("Trials", self.trials_spin)
        simulation_form.addRow("Max rounds", self.max_rounds_spin)
        simulation_form.addRow("Seed", self.seed_controls_widget)
        simulation_form.addRow("", self.run_controls_widget)
        simulation_group.setLayout(simulation_form)
        self._simulation_group = simulation_group

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.team_one_editor, stretch=3)
        controls_layout.addWidget(self.team_two_editor, stretch=3)
        controls_layout.addWidget(simulation_group, stretch=2)

        note_label = QLabel(
            "Set up both teams using the combatant cards, then choose trial count, max rounds, "
            "and an optional seed in Simulation Setup, then run the simulation to generate team "
            "battle results. Use the Reference Strike panel to inspect an exact one-attack result."
        )
        note_label.setWordWrap(True)

        self.hit_label = QLabel()
        self.raw_damage_label = QLabel()
        self.post_armor_damage_label = QLabel()
        self.no_injury_label = QLabel()
        self.minor_injury_label = QLabel()
        self.major_injury_label = QLabel()
        self.unconscious_label = QLabel()
        self.reference_attacker_combo = QComboBox()
        self.reference_defender_combo = QComboBox()
        self.reference_attacker_combo.currentIndexChanged.connect(
            self._refresh_reference_strike_display
        )
        self.reference_defender_combo.currentIndexChanged.connect(
            self._refresh_reference_strike_display
        )

        self.reference_group = QGroupBox("Reference Strike (Exact)")
        opening_form = QFormLayout()
        opening_form.addRow("Attacker", self.reference_attacker_combo)
        opening_form.addRow("Defender", self.reference_defender_combo)
        opening_form.addRow("P(hit this attack)", self.hit_label)
        opening_form.addRow("Expected raw damage", self.raw_damage_label)
        opening_form.addRow("Expected damage after armor", self.post_armor_damage_label)
        opening_form.addRow("P(no injury)", self.no_injury_label)
        opening_form.addRow("P(minor injury)", self.minor_injury_label)
        opening_form.addRow("P(major injury)", self.major_injury_label)
        opening_form.addRow("P(unconscious)", self.unconscious_label)
        self.reference_group.setLayout(opening_form)

        self.team_one_win_rate_label = QLabel()
        self.team_two_win_rate_label = QLabel()
        self.unresolved_rate_label = QLabel()
        self.average_rounds_label = QLabel()

        self.team_battle_results_group = QGroupBox("Team Battle Results (Simulated)")
        duel_form = QFormLayout()
        duel_form.addRow("Team 1 win rate", self.team_one_win_rate_label)
        duel_form.addRow("Team 2 win rate", self.team_two_win_rate_label)
        duel_form.addRow("Unresolved after max rounds", self.unresolved_rate_label)
        duel_form.addRow("Average rounds to resolution (resolved only)", self.average_rounds_label)
        self.team_battle_results_group.setLayout(duel_form)

        summary_layout = QHBoxLayout()
        summary_layout.addWidget(self.reference_group, stretch=1)
        summary_layout.addWidget(self.team_battle_results_group, stretch=1)

        self.round_table = QTableWidget(0, 7)
        self.round_table.setHorizontalHeaderLabels(
            [
                "Round",
                "T2 avg KOs",
                "T2 avg minor",
                "T2 avg major",
                "T2 defeated",
                "T1 avg KOs",
                "T1 defeated",
            ]
        )
        self.round_table.verticalHeader().setVisible(False)
        self.round_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.round_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.round_table.setMinimumHeight(220)

        self.content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.addLayout(controls_layout, stretch=3)
        content_layout.addWidget(note_label)
        content_layout.addLayout(summary_layout, stretch=1)
        content_layout.addWidget(QLabel("Round-by-round team state summary"))
        content_layout.addWidget(self.round_table, stretch=2)
        self.content_widget.setLayout(content_layout)

        self.content_scroll_area = QScrollArea()
        self.content_scroll_area.setWidgetResizable(True)
        self.content_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll_area.setWidget(self.content_widget)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.menu_bar)
        layout.addWidget(self.content_scroll_area, stretch=1)
        self.setLayout(layout)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._wait_for_simulation_thread)

        self._refresh_reference_selectors_from_editors()
        self._clear_team_battle_results_display()

    def _build_menu_bar(self) -> None:
        presets_menu = self.menu_bar.addMenu("Presets")
        share_menu = self.menu_bar.addMenu("Share")

        save_to_library_action = QAction("Save To Library...", self)
        save_to_library_action.triggered.connect(self._save_preset_to_library)
        presets_menu.addAction(save_to_library_action)

        save_json_action = QAction("Save JSON As...", self)
        save_json_action.triggered.connect(self._save_preset_json_as)
        presets_menu.addAction(save_json_action)

        presets_menu.addSeparator()

        load_from_library_action = QAction("Load From Library...", self)
        load_from_library_action.triggered.connect(self._load_preset_from_library)
        presets_menu.addAction(load_from_library_action)

        load_json_action = QAction("Load JSON...", self)
        load_json_action.triggered.connect(self._load_preset_json)
        presets_menu.addAction(load_json_action)

        delete_from_library_action = QAction("Delete From Library...", self)
        delete_from_library_action.triggered.connect(self._delete_preset_from_library)
        presets_menu.addAction(delete_from_library_action)

        export_share_action = QAction("Export Share String...", self)
        export_share_action.triggered.connect(self._export_preset_share_string)
        share_menu.addAction(export_share_action)

        import_share_action = QAction("Import Share String...", self)
        import_share_action.triggered.connect(self._import_preset_share_string)
        share_menu.addAction(import_share_action)

    def _ensure_preset_directory(self) -> Path:
        try:
            self._preset_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            msg = f"Could not create preset directory:\n{self._preset_directory}\n\n{exc}"
            raise PresetCodecError(msg) from exc
        return self._preset_directory

    def _app_preset_paths(self) -> tuple[Path, ...]:
        directory = self._ensure_preset_directory()
        return tuple(
            sorted(
                (path for path in directory.glob("*.json") if path.is_file()),
                key=lambda path: path.name.lower(),
            )
        )

    def _default_reference_selection(self, preferred_team: int) -> CombatantReference:
        key = self._reference_key_by_position.get((preferred_team, 0))
        if key is None:
            key = self._reference_key_by_position.get((1, 0))
        if key is None:
            key = self._reference_key_by_position.get((2, 0))
        selection = self._reference_selection_by_key.get(key) if key is not None else None
        if selection is not None:
            return selection
        return CombatantReference(team_number=1, combatant_index=0)

    def _current_reference_selection(
        self,
        combo: QComboBox,
        preferred_team: int,
    ) -> CombatantReference:
        selection = self._reference_selection_by_key.get(combo.currentData())
        if selection is not None:
            return selection
        return self._default_reference_selection(preferred_team)

    def _set_reference_selection(
        self,
        combo: QComboBox,
        selection: CombatantReference,
        preferred_team: int,
    ) -> None:
        key = self._reference_key_by_position.get(
            (selection.team_number, selection.combatant_index)
        )
        if key is None:
            fallback = self._default_reference_selection(preferred_team)
            key = self._reference_key_by_position.get(
                (fallback.team_number, fallback.combatant_index)
            )
        if key is None:
            return
        combo_index = combo.findData(key)
        if combo_index >= 0:
            combo.setCurrentIndex(combo_index)

    def _build_current_preset(self) -> CombatSimulatorPreset:
        team_one = self.team_one_editor.build_team()
        team_two = self.team_two_editor.build_team()
        self._refresh_reference_selectors_from_editors()
        return CombatSimulatorPreset(
            team_one=team_one,
            team_two=team_two,
            simulation=DuelSimulationConfig(
                trials=self.trials_spin.value(),
                max_rounds=self.max_rounds_spin.value(),
                seed=self._parse_seed(),
            ),
            reference_attacker=self._current_reference_selection(
                self.reference_attacker_combo,
                preferred_team=1,
            ),
            reference_defender=self._current_reference_selection(
                self.reference_defender_combo,
                preferred_team=2,
            ),
        )

    def _apply_preset(self, preset: CombatSimulatorPreset) -> None:
        self.team_one_editor.load_team(preset.team_one)
        self.team_two_editor.load_team(preset.team_two)
        self.trials_spin.setValue(preset.simulation.trials)
        self.max_rounds_spin.setValue(preset.simulation.max_rounds)
        self._set_seed_value(-1 if preset.simulation.seed is None else preset.simulation.seed)
        self._refresh_reference_selectors_from_editors()
        self._set_reference_selection(
            self.reference_attacker_combo,
            preset.reference_attacker,
            preferred_team=1,
        )
        self._set_reference_selection(
            self.reference_defender_combo,
            preset.reference_defender,
            preferred_team=2,
        )
        self._refresh_reference_strike_display()
        self._last_result = None
        self._clear_team_battle_results_display()
        self.run_progress_bar.setValue(0)
        self.run_progress_bar.setFormat("Running simulation... %p%")

    def _confirm_overwrite(self, path: Path) -> bool:
        response = QMessageBox.question(
            self,
            "Overwrite Preset?",
            f"A preset already exists at:\n{path}\n\nOverwrite it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _confirm_delete(self, path: Path) -> bool:
        response = QMessageBox.question(
            self,
            "Delete Preset?",
            f"Delete preset '{path.name}' from the app preset directory?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _save_current_preset_to_path(self, path: Path) -> None:
        try:
            saved_path = save_combat_simulator_preset_file(self._build_current_preset(), path)
        except PresetCodecError as exc:
            QMessageBox.warning(self, "Preset Save Failed", str(exc))
            return
        QMessageBox.information(self, "Preset Saved", f"Preset saved to:\n{saved_path}")

    def _load_preset_from_path(self, path: Path) -> None:
        try:
            preset = load_combat_simulator_preset_file(path)
        except PresetCodecError as exc:
            QMessageBox.warning(self, "Preset Load Failed", str(exc))
            return
        self._apply_preset(preset)

    def _save_preset_to_library(self) -> None:
        preset_name, accepted = QInputDialog.getText(
            self,
            "Save Preset To Library",
            "Preset name:",
        )
        if not accepted:
            return
        try:
            destination = self._ensure_preset_directory() / app_preset_file_name(preset_name)
        except PresetCodecError as exc:
            QMessageBox.warning(self, "Preset Save Failed", str(exc))
            return
        if destination.exists() and not self._confirm_overwrite(destination):
            return
        self._save_current_preset_to_path(destination)

    def _save_preset_json_as(self) -> None:
        try:
            default_path = self._ensure_preset_directory() / "combat-preset.json"
        except PresetCodecError as exc:
            QMessageBox.warning(self, "Preset Save Failed", str(exc))
            return
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Preset JSON",
            str(default_path),
            "JSON Files (*.json);;All Files (*)",
        )
        if not selected_path:
            return
        destination = Path(selected_path)
        if destination.suffix.lower() != ".json":
            destination = destination.with_suffix(".json")
        if destination.exists() and not self._confirm_overwrite(destination):
            return
        self._save_current_preset_to_path(destination)

    def _choose_app_preset_path(self, title: str, prompt: str) -> Path | None:
        try:
            preset_paths = self._app_preset_paths()
        except PresetCodecError as exc:
            QMessageBox.warning(self, title, str(exc))
            return None
        if not preset_paths:
            QMessageBox.information(
                self,
                title,
                f"No presets were found in:\n{self._preset_directory}",
            )
            return None
        selection, accepted = QInputDialog.getItem(
            self,
            title,
            prompt,
            [path.name for path in preset_paths],
            0,
            False,
        )
        if not accepted or not selection:
            return None
        for path in preset_paths:
            if path.name == selection:
                return path
        return None

    def _load_preset_from_library(self) -> None:
        selected_path = self._choose_app_preset_path(
            "Load Preset From Library",
            "Preset:",
        )
        if selected_path is not None:
            self._load_preset_from_path(selected_path)

    def _load_preset_json(self) -> None:
        try:
            default_directory = self._ensure_preset_directory()
        except PresetCodecError as exc:
            QMessageBox.warning(self, "Preset Load Failed", str(exc))
            return
        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Load Preset JSON",
            str(default_directory),
            "JSON Files (*.json);;All Files (*)",
        )
        if selected_path:
            self._load_preset_from_path(Path(selected_path))

    def _delete_preset_from_library(self) -> None:
        selected_path = self._choose_app_preset_path(
            "Delete Preset From Library",
            "Preset:",
        )
        if selected_path is None or not self._confirm_delete(selected_path):
            return
        try:
            selected_path.unlink()
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Preset Delete Failed",
                f"Could not delete preset '{selected_path.name}':\n{exc}",
            )
            return
        QMessageBox.information(self, "Preset Deleted", f"Deleted preset '{selected_path.name}'.")

    def _export_preset_share_string(self) -> None:
        try:
            share_string = encode_combat_simulator_preset_share_string(
                self._build_current_preset()
            )
        except PresetCodecError as exc:
            QMessageBox.warning(self, "Preset Export Failed", str(exc))
            return
        dialog = _ShareStringDialog(share_string, self)
        dialog.exec()

    def _import_preset_share_string(self) -> None:
        share_string, accepted = QInputDialog.getMultiLineText(
            self,
            "Import Preset String",
            "Paste preset string:",
        )
        if not accepted or not share_string.strip():
            return
        try:
            preset = decode_combat_simulator_preset_share_string(share_string)
        except PresetCodecError as exc:
            QMessageBox.warning(self, "Preset Import Failed", str(exc))
            return
        self._apply_preset(preset)

    def _parse_seed(self) -> int | None:
        if self.seed_spin.value() < 0:
            return None
        return int(self.seed_spin.value())

    def _set_seed_value(self, seed_value: int) -> None:
        self.seed_spin.setValue(max(-1, seed_value))

    def _randomize_seed(self) -> None:
        self._set_seed_value(random.randint(0, 999_999_999))

    def _reference_key(self, team_number: int, card_key: str) -> str:
        return f"team{team_number}:{card_key}"

    def _clear_team_battle_results_display(self) -> None:
        for label in (
            self.team_one_win_rate_label,
            self.team_two_win_rate_label,
            self.unresolved_rate_label,
            self.average_rounds_label,
        ):
            label.setText(RUN_SIMULATION_PROMPT)
        self.round_table.setRowCount(0)

    def _clear_reference_strike_display(self) -> None:
        for label in (
            self.hit_label,
            self.raw_damage_label,
            self.post_armor_damage_label,
            self.no_injury_label,
            self.minor_injury_label,
            self.major_injury_label,
            self.unconscious_label,
        ):
            label.setText("n/a")

    def _populate_reference_selectors(
        self,
        team_one_snapshots: tuple[tuple[str, Combatant], ...],
        team_two_snapshots: tuple[tuple[str, Combatant], ...],
    ) -> None:
        previous_attacker_key = self.reference_attacker_combo.currentData()
        previous_defender_key = self.reference_defender_combo.currentData()

        team_one_entries = [
            (
                self._reference_key(1, card_key),
                f"Team 1: {combatant.name}",
                combatant,
                CombatantReference(team_number=1, combatant_index=index),
            )
            for index, (card_key, combatant) in enumerate(team_one_snapshots)
        ]
        team_two_entries = [
            (
                self._reference_key(2, card_key),
                f"Team 2: {combatant.name}",
                combatant,
                CombatantReference(team_number=2, combatant_index=index),
            )
            for index, (card_key, combatant) in enumerate(team_two_snapshots)
        ]

        self._reference_combatants = {
            key: combatant for key, _, combatant, _ in (*team_one_entries, *team_two_entries)
        }
        self._reference_selection_by_key = {
            key: selection
            for key, _label, _combatant, selection in (*team_one_entries, *team_two_entries)
        }
        self._reference_key_by_position = {
            (selection.team_number, selection.combatant_index): key
            for key, _label, _combatant, selection in (*team_one_entries, *team_two_entries)
        }

        for combo in (self.reference_attacker_combo, self.reference_defender_combo):
            combo.blockSignals(True)
            combo.clear()
            for key, label, _combatant, _selection in team_one_entries:
                combo.addItem(label, key)
            if team_one_entries and team_two_entries:
                combo.insertSeparator(combo.count())
            for key, label, _combatant, _selection in team_two_entries:
                combo.addItem(label, key)
            combo.blockSignals(False)

        default_attacker_key = team_one_entries[0][0] if team_one_entries else None
        default_defender_key = team_two_entries[0][0] if team_two_entries else default_attacker_key
        attacker_key = previous_attacker_key or default_attacker_key
        defender_key = previous_defender_key or default_defender_key

        attacker_index = (
            self.reference_attacker_combo.findData(attacker_key) if attacker_key is not None else -1
        )
        defender_index = (
            self.reference_defender_combo.findData(defender_key) if defender_key is not None else -1
        )
        if attacker_index < 0 and default_attacker_key is not None:
            attacker_index = self.reference_attacker_combo.findData(default_attacker_key)
        if defender_index < 0 and default_defender_key is not None:
            defender_index = self.reference_defender_combo.findData(default_defender_key)

        if attacker_index >= 0:
            self.reference_attacker_combo.setCurrentIndex(attacker_index)
        if defender_index >= 0:
            self.reference_defender_combo.setCurrentIndex(defender_index)

        self._refresh_reference_strike_display()

    def _refresh_reference_selectors_from_editors(self) -> None:
        self._populate_reference_selectors(
            self.team_one_editor.combatant_snapshots(),
            self.team_two_editor.combatant_snapshots(),
        )

    def _refresh_reference_strike_display(self) -> None:
        attacker = self._reference_combatants.get(self.reference_attacker_combo.currentData())
        defender = self._reference_combatants.get(self.reference_defender_combo.currentData())
        if attacker is None or defender is None:
            self._clear_reference_strike_display()
            return

        reference_strike = analyze_opening_attack(attacker, defender)
        self.hit_label.setText(_format_probability(reference_strike.hit_probability))
        self.raw_damage_label.setText(f"{float(reference_strike.expected_incoming_damage):.6f}")
        self.post_armor_damage_label.setText(
            f"{float(reference_strike.expected_damage_after_armor):.6f}"
        )
        self.no_injury_label.setText(_format_probability(reference_strike.probability_no_injury))
        self.minor_injury_label.setText(
            _format_probability(reference_strike.probability_minor_injury)
        )
        self.major_injury_label.setText(
            _format_probability(reference_strike.probability_major_injury)
        )
        self.unconscious_label.setText(
            _format_probability(reference_strike.probability_unconscious)
        )

    def _populate_round_table(self, result: TeamBattleSimulationResult) -> None:
        self.round_table.setRowCount(len(result.round_summaries))
        for row_index, round_summary in enumerate(result.round_summaries):
            _set_centered_item(self.round_table, row_index, 0, str(round_summary.round_number))
            _set_centered_item(
                self.round_table,
                row_index,
                1,
                f"{round_summary.team_two.average_unconscious_combatants:.3f}",
            )
            _set_centered_item(
                self.round_table,
                row_index,
                2,
                f"{round_summary.team_two.average_minor_injuries:.3f}",
            )
            _set_centered_item(
                self.round_table,
                row_index,
                3,
                f"{round_summary.team_two.average_major_injuries:.3f}",
            )
            _set_centered_item(
                self.round_table,
                row_index,
                4,
                _format_probability(round_summary.team_two.probability_team_defeated),
            )
            _set_centered_item(
                self.round_table,
                row_index,
                5,
                f"{round_summary.team_one.average_unconscious_combatants:.3f}",
            )
            _set_centered_item(
                self.round_table,
                row_index,
                6,
                _format_probability(round_summary.team_one.probability_team_defeated),
            )

        self.round_table.resizeColumnsToContents()

    def _set_simulation_running(self, running: bool) -> None:
        self.menu_bar.setEnabled(not running)
        self.team_one_editor.setEnabled(not running)
        self.team_two_editor.setEnabled(not running)
        self.reference_attacker_combo.setEnabled(not running)
        self.reference_defender_combo.setEnabled(not running)
        self.trials_spin.setEnabled(not running)
        self.max_rounds_spin.setEnabled(not running)
        self.seed_controls_widget.setEnabled(not running)
        self.run_controls_layout.setCurrentWidget(
            self.run_progress_bar if running else self.run_button
        )

    def _update_simulation_progress(self, completed_trials: int, total_trials: int) -> None:
        if total_trials <= 0:
            return
        progress_percent = int((completed_trials / total_trials) * 100)
        self.run_progress_bar.setValue(progress_percent)
        self.run_progress_bar.setFormat(
            f"Running simulation... {completed_trials}/{total_trials} (%p%)"
        )

    def _cleanup_simulation_thread(self) -> None:
        if self._simulation_thread is None:
            return
        self._simulation_thread.deleteLater()
        self._simulation_thread = None

    def _wait_for_simulation_thread(self) -> None:
        if self._simulation_thread is not None and self._simulation_thread.isRunning():
            self._simulation_thread.wait()

    def _handle_simulation_failure(self, details: str) -> None:
        self._set_simulation_running(False)
        self._cleanup_simulation_thread()
        QMessageBox.critical(
            self,
            "Simulation Failed",
            f"The combat simulation encountered an unexpected error.\n\n{details}",
        )

    def _handle_simulation_result(self, result: TeamBattleSimulationResult) -> None:
        self._last_result = result

        self.team_one_win_rate_label.setText(_format_probability(result.team_one_win_rate))
        self.team_two_win_rate_label.setText(_format_probability(result.team_two_win_rate))
        self.unresolved_rate_label.setText(_format_probability(result.unresolved_rate))
        if result.average_rounds_to_resolution is None:
            self.average_rounds_label.setText("n/a")
        else:
            self.average_rounds_label.setText(f"{result.average_rounds_to_resolution:.3f}")

        self._populate_round_table(result)

    def _handle_simulation_finished(self) -> None:
        self._set_simulation_running(False)
        self._cleanup_simulation_thread()

    def run_simulation(self) -> None:
        if self._simulation_thread is not None and self._simulation_thread.isRunning():
            return

        try:
            config = DuelSimulationConfig(
                trials=self.trials_spin.value(),
                max_rounds=self.max_rounds_spin.value(),
                seed=self._parse_seed(),
            )
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Seed",
                "Seed must be blank or a whole number.",
            )
            return

        team_one = self.team_one_editor.build_team()
        team_two = self.team_two_editor.build_team()
        self._refresh_reference_selectors_from_editors()
        self._set_simulation_running(True)
        self._update_simulation_progress(0, config.trials)

        self._simulation_thread = _TeamBattleSimulationThread(team_one, team_two, config)
        self._simulation_thread.progress_changed.connect(self._update_simulation_progress)
        self._simulation_thread.result_ready.connect(self._handle_simulation_result)
        self._simulation_thread.failed.connect(self._handle_simulation_failure)
        self._simulation_thread.finished.connect(self._handle_simulation_finished)
        self._simulation_thread.start()
