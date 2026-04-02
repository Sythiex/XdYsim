from __future__ import annotations

from xdysim.gui.combat_simulator_tab import unique_combatant_name


def test_unique_combatant_name_numbers_plain_duplicate_names() -> None:
    assert unique_combatant_name("Attacker", {"Attacker"}, "Attacker 1") == "Attacker 2"


def test_unique_combatant_name_keeps_incrementing_numbered_duplicates() -> None:
    taken_names = {"Attacker", "Attacker 2", "Attacker 3"}

    assert unique_combatant_name("Attacker", taken_names, "Attacker 1") == "Attacker 4"
    assert unique_combatant_name("Attacker 2", taken_names, "Attacker 1") == "Attacker 4"


def test_unique_combatant_name_uses_fallback_when_name_is_blank() -> None:
    assert unique_combatant_name("", {"Defender 1"}, "Defender 1") == "Defender 2"
