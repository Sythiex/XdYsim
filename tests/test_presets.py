from __future__ import annotations

import json
from pathlib import Path

import pytest

from xdysim.engine import (
    SHARE_STRING_PREFIX,
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
    app_preset_file_name,
    decode_combat_simulator_preset_share_string,
    default_app_preset_directory,
    deserialize_combat_simulator_preset_json,
    encode_combat_simulator_preset_share_string,
    load_combat_simulator_preset_file,
    save_combat_simulator_preset_file,
    serialize_combat_simulator_preset_json,
)


def _sample_preset() -> CombatSimulatorPreset:
    return CombatSimulatorPreset(
        team_one=CombatTeam(
            name="Team 1",
            combatants=(
                Combatant(
                    name="Alpha",
                    combat=CombatProfile(
                        attack_skill_rank=SkillRank.FOUR,
                        defense_skill_rank=SkillRank.THREE,
                        initiative_skill_rank=SkillRank.TWO,
                    ),
                    armor=Armor(rating=1),
                    injury_track=InjuryTrack(minor_capacity=3, major_capacity=2),
                ),
                Combatant(
                    name="Beta",
                    combat=CombatProfile(
                        attack_skill_rank=SkillRank.TWO,
                        defense_skill_rank=SkillRank.FIVE,
                        initiative_skill_rank=SkillRank.SIX,
                    ),
                    armor=Armor(rating=0),
                    injury_track=InjuryTrack(minor_capacity=1, major_capacity=4),
                ),
            ),
        ),
        team_two=CombatTeam(
            name="Team 2",
            combatants=(
                Combatant(
                    name="Gamma",
                    combat=CombatProfile(
                        attack_skill_rank=SkillRank.SIX,
                        defense_skill_rank=SkillRank.ONE,
                        initiative_skill_rank=SkillRank.FIVE,
                    ),
                    armor=Armor(rating=2),
                    injury_track=InjuryTrack(minor_capacity=2, major_capacity=1),
                ),
            ),
        ),
        simulation=DuelSimulationConfig(trials=12_000, max_rounds=75, seed=123456),
        reference_attacker=CombatantReference(team_number=1, combatant_index=1),
        reference_defender=CombatantReference(team_number=2, combatant_index=0),
    )


def test_preset_json_round_trip() -> None:
    preset = _sample_preset()

    assert deserialize_combat_simulator_preset_json(
        serialize_combat_simulator_preset_json(preset)
    ) == preset


def test_preset_file_round_trip(tmp_path) -> None:
    preset = _sample_preset()
    destination = tmp_path / "duel.json"

    saved_path = save_combat_simulator_preset_file(preset, destination)

    assert saved_path == destination
    assert load_combat_simulator_preset_file(destination) == preset


def test_preset_share_string_round_trip() -> None:
    preset = _sample_preset()

    share_string = encode_combat_simulator_preset_share_string(preset)

    assert share_string.startswith(SHARE_STRING_PREFIX)
    assert decode_combat_simulator_preset_share_string(share_string) == preset


def test_deserialize_preset_json_rejects_unsupported_schema_version() -> None:
    preset_payload = json.loads(serialize_combat_simulator_preset_json(_sample_preset()))
    preset_payload["schema_version"] = 99

    with pytest.raises(PresetCodecError, match="Unsupported preset schema version: 99"):
        deserialize_combat_simulator_preset_json(json.dumps(preset_payload))


def test_decode_preset_share_string_rejects_invalid_or_truncated_text() -> None:
    with pytest.raises(PresetCodecError, match="invalid or truncated"):
        decode_combat_simulator_preset_share_string("xdysim-preset-v1:not-valid")


def test_decode_preset_share_string_rejects_unsupported_version() -> None:
    with pytest.raises(PresetCodecError, match="Unsupported preset string format version: 9"):
        decode_combat_simulator_preset_share_string("xdysim-preset-v9:abcd")


def test_preset_file_name_is_sanitized_for_library_storage() -> None:
    assert app_preset_file_name('Boss: Fight? "Final"') == "Boss_ Fight_ _Final_.json"


def test_default_app_preset_directory_prefers_project_root_in_repo(monkeypatch) -> None:
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)

    assert default_app_preset_directory() == project_root / "presets"
