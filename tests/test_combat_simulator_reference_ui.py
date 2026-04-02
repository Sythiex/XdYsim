from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from xdysim.gui.combat_simulator_tab import CombatSimulatorTab


def _application() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _finish_initial_run(tab: CombatSimulatorTab) -> None:
    _application().processEvents()


def test_combat_simulator_does_not_run_on_startup() -> None:
    _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    assert tab._simulation_thread is None
    assert tab.team_one_win_rate_label.text() == "Run a simulation"
    assert tab.team_two_win_rate_label.text() == "Run a simulation"
    assert tab.round_table.rowCount() == 0


def test_preset_menu_bar_has_visual_styling() -> None:
    _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    assert not tab.menu_bar.isNativeMenuBar()
    assert "QMenuBar::item" in tab.menu_bar.styleSheet()


def test_combat_tab_scrolls_instead_of_overlapping_at_small_heights() -> None:
    app = _application()
    tab = CombatSimulatorTab()
    tab.resize(1500, 600)
    tab.show()
    _finish_initial_run(tab)
    app.processEvents()

    assert tab.content_scroll_area.verticalScrollBar().maximum() > 0
    assert tab.team_one_editor.geometry().bottom() < tab.reference_group.geometry().top()


def test_reference_selectors_show_team_order_with_separator() -> None:
    _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    combo = tab.reference_attacker_combo
    model = combo.model()

    assert combo.count() == 3
    assert combo.itemText(0) == "Team 1: Team 1 1"
    assert combo.itemText(2) == "Team 2: Team 2 1"

    separator_flags = model.flags(model.index(1, 0))
    assert not separator_flags & Qt.ItemFlag.ItemIsEnabled


def test_reference_strike_allows_self_target_selection() -> None:
    _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    tab.reference_attacker_combo.setCurrentIndex(0)
    tab.reference_defender_combo.setCurrentIndex(0)
    tab._refresh_reference_strike_display()

    assert tab.hit_label.text().endswith("%")


def test_reference_selectors_refresh_when_team_list_changes_without_running_simulation() -> None:
    _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    tab.team_one_editor.add_card()

    combo = tab.reference_attacker_combo

    assert combo.count() == 4
    assert combo.itemText(0) == "Team 1: Team 1 1"
    assert combo.itemText(1) == "Team 1: Team 1 2"
    assert combo.itemText(3) == "Team 2: Team 2 1"


def test_drag_preview_removes_card_from_list_and_shows_indicator() -> None:
    app = _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    tab.team_one_editor.add_card()
    app.processEvents()

    editor = tab.team_one_editor
    dragged_card = editor._cards[0]

    editor._begin_drag(dragged_card)

    assert dragged_card not in editor._cards
    assert not dragged_card.isVisible()
    assert editor.cards_layout.indexOf(editor._drop_indicator) != -1
    assert not editor._drop_indicator.isHidden()

    editor._restore_active_drag()
    type(editor)._active_drag_state = None
    editor._clear_drop_indicator()


def test_drag_drop_can_move_card_between_teams() -> None:
    app = _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    tab.team_one_editor.add_card()
    app.processEvents()

    source_editor = tab.team_one_editor
    target_editor = tab.team_two_editor
    moved_card = source_editor._cards[1]

    source_editor._begin_drag(moved_card)
    target_editor.preview_drop(0)
    target_editor.drop_card(0)
    app.processEvents()

    assert moved_card not in source_editor._cards
    assert moved_card in target_editor._cards
    assert moved_card is target_editor._cards[0]
    assert moved_card._team_editor is target_editor


def test_seed_controls_support_increment_decrement_and_randomize() -> None:
    app = _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    tab.seed_spin.setValue(-1)
    tab.seed_spin.stepUp()
    app.processEvents()
    assert tab.seed_spin.value() == 0

    tab.seed_spin.stepDown()
    app.processEvents()
    assert tab.seed_spin.value() == -1

    tab.seed_randomize_button.click()
    app.processEvents()
    assert tab.seed_spin.value() >= 0


def test_combatant_track_fields_allow_values_up_to_99() -> None:
    _application()
    tab = CombatSimulatorTab()
    _finish_initial_run(tab)

    card = tab.team_one_editor._cards[0]

    assert card.armor_spin.maximum() == 99
    assert card.minor_capacity_spin.maximum() == 99
    assert card.major_capacity_spin.maximum() == 99


def test_preset_round_trip_restores_combat_simulator_state(tmp_path) -> None:
    app = _application()
    tab = CombatSimulatorTab(preset_directory=tmp_path)
    _finish_initial_run(tab)

    tab.team_one_editor.add_card()
    tab.team_two_editor.add_card()
    app.processEvents()

    team_one_first = tab.team_one_editor._cards[0]
    team_one_second = tab.team_one_editor._cards[1]
    team_two_first = tab.team_two_editor._cards[0]
    team_two_second = tab.team_two_editor._cards[1]

    team_one_first.name_edit.setText("Alpha")
    team_one_first.attack_rank_combo.setCurrentIndex(3)
    team_one_first.defense_rank_combo.setCurrentIndex(2)
    team_one_first.initiative_rank_combo.setCurrentIndex(1)
    team_one_first.armor_spin.setValue(1)
    team_one_first.minor_capacity_spin.setValue(3)
    team_one_first.major_capacity_spin.setValue(2)

    team_one_second.name_edit.setText("Bravo")
    team_one_second.attack_rank_combo.setCurrentIndex(5)
    team_one_second.defense_rank_combo.setCurrentIndex(4)
    team_one_second.initiative_rank_combo.setCurrentIndex(3)
    team_one_second.armor_spin.setValue(2)
    team_one_second.minor_capacity_spin.setValue(1)
    team_one_second.major_capacity_spin.setValue(4)

    team_two_first.name_edit.setText("Gamma")
    team_two_first.attack_rank_combo.setCurrentIndex(2)
    team_two_first.defense_rank_combo.setCurrentIndex(0)
    team_two_first.initiative_rank_combo.setCurrentIndex(5)
    team_two_first.armor_spin.setValue(0)
    team_two_first.minor_capacity_spin.setValue(2)
    team_two_first.major_capacity_spin.setValue(1)

    team_two_second.name_edit.setText("Delta")
    team_two_second.attack_rank_combo.setCurrentIndex(1)
    team_two_second.defense_rank_combo.setCurrentIndex(5)
    team_two_second.initiative_rank_combo.setCurrentIndex(4)
    team_two_second.armor_spin.setValue(3)
    team_two_second.minor_capacity_spin.setValue(4)
    team_two_second.major_capacity_spin.setValue(3)

    tab.trials_spin.setValue(12_300)
    tab.max_rounds_spin.setValue(88)
    tab.seed_spin.setValue(7654321)
    app.processEvents()

    tab.reference_attacker_combo.setCurrentIndex(1)
    tab.reference_defender_combo.setCurrentIndex(4)
    app.processEvents()

    preset = tab._build_current_preset()

    restored = CombatSimulatorTab(preset_directory=tmp_path)
    restored._apply_preset(preset)
    _finish_initial_run(restored)

    assert restored._build_current_preset() == preset
    assert restored.team_one_win_rate_label.text() == "Run a simulation"
    assert restored.round_table.rowCount() == 0
