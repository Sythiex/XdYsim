from __future__ import annotations

import pytest

from xdysim.engine import (
    Armor,
    Combatant,
    CombatProfile,
    CombatTeam,
    DuelSimulationConfig,
    InjuryTrack,
    SkillRank,
    simulate_team_battle,
)


def _combatant(
    name: str,
    attack_rank: SkillRank,
    *,
    defense_rank: SkillRank | None = None,
    initiative_rank: SkillRank | None = None,
    armor: int = 0,
    minor_capacity: int = 2,
    major_capacity: int = 2,
) -> Combatant:
    return Combatant(
        name=name,
        combat=CombatProfile(
            attack_skill_rank=attack_rank,
            defense_skill_rank=defense_rank or attack_rank,
            initiative_skill_rank=initiative_rank or attack_rank,
        ),
        armor=Armor(rating=armor),
        injury_track=InjuryTrack(
            minor_capacity=minor_capacity,
            major_capacity=major_capacity,
        ),
    )


def _team(name: str, *combatants: Combatant) -> CombatTeam:
    return CombatTeam(name=name, combatants=tuple(combatants))


def test_team_battle_is_seeded_and_repeatable() -> None:
    team_one = _team(
        "Team 1",
        _combatant("Team 1 A", SkillRank.FOUR, armor=1),
        _combatant("Team 1 B", SkillRank.THREE, armor=1),
    )
    team_two = _team(
        "Team 2",
        _combatant("Team 2 A", SkillRank.THREE, armor=1),
        _combatant("Team 2 B", SkillRank.THREE, armor=1),
    )
    config = DuelSimulationConfig(trials=1_500, max_rounds=10, seed=23)

    first = simulate_team_battle(team_one, team_two, config)
    second = simulate_team_battle(team_one, team_two, config)

    assert first.model_dump() == second.model_dump()


def test_team_battle_outputs_well_formed_probabilities() -> None:
    team_one = _team(
        "Team 1",
        _combatant("Team 1 A", SkillRank.FOUR, armor=1),
        _combatant("Team 1 B", SkillRank.TWO, armor=0),
    )
    team_two = _team(
        "Team 2",
        _combatant("Team 2 A", SkillRank.THREE, armor=1),
        _combatant("Team 2 B", SkillRank.THREE, armor=0),
    )
    result = simulate_team_battle(
        team_one,
        team_two,
        DuelSimulationConfig(trials=2_000, max_rounds=10, seed=29),
    )

    assert len(result.round_summaries) == 10
    assert (
        result.team_one_win_rate + result.team_two_win_rate + result.unresolved_rate
        == pytest.approx(1.0)
    )

    previous_team_two_defeat = 0.0
    previous_team_one_defeat = 0.0
    for round_summary in result.round_summaries:
        assert round_summary.team_two.probability_team_defeated >= previous_team_two_defeat
        assert round_summary.team_one.probability_team_defeated >= previous_team_one_defeat
        previous_team_two_defeat = round_summary.team_two.probability_team_defeated
        previous_team_one_defeat = round_summary.team_one.probability_team_defeated


def test_extra_teammate_improves_team_results() -> None:
    solo_team = _team(
        "Solo Team",
        _combatant("Solo", SkillRank.FOUR, armor=1),
    )
    duo_team = _team(
        "Duo Team",
        _combatant("Lead", SkillRank.FOUR, armor=1),
        _combatant("Reserve", SkillRank.FOUR, armor=1),
    )
    team_two = _team(
        "Team 2",
        _combatant("Opponent", SkillRank.FOUR, armor=1),
    )
    config = DuelSimulationConfig(trials=2_000, max_rounds=10, seed=31)

    solo_result = simulate_team_battle(solo_team, team_two, config)
    duo_result = simulate_team_battle(duo_team, team_two, config)

    assert duo_result.team_one_win_rate > solo_result.team_one_win_rate


def test_higher_initiative_improves_otherwise_equal_duel_results() -> None:
    fast_team = _team(
        "Fast Team",
        _combatant(
            "Fast",
            SkillRank.SIX,
            defense_rank=SkillRank.ONE,
            initiative_rank=SkillRank.SIX,
            armor=0,
            minor_capacity=0,
            major_capacity=0,
        ),
    )
    slow_team = _team(
        "Slow Team",
        _combatant(
            "Slow",
            SkillRank.SIX,
            defense_rank=SkillRank.ONE,
            initiative_rank=SkillRank.ONE,
            armor=0,
            minor_capacity=0,
            major_capacity=0,
        ),
    )
    config = DuelSimulationConfig(trials=3_000, max_rounds=5, seed=37)

    fast_result = simulate_team_battle(fast_team, slow_team, config)
    slow_result = simulate_team_battle(slow_team, fast_team, config)

    assert fast_result.team_one_win_rate > 0.5
    assert fast_result.team_one_win_rate > slow_result.team_two_win_rate


def test_reference_strike_uses_first_listed_combatants() -> None:
    team_one = _team(
        "Team 1",
        _combatant("Novice", SkillRank.ONE),
        _combatant("Elite", SkillRank.SIX),
    )
    team_two = _team(
        "Team 2",
        _combatant("Guard", SkillRank.THREE, defense_rank=SkillRank.FOUR),
    )

    result = simulate_team_battle(
        team_one,
        team_two,
        DuelSimulationConfig(trials=500, max_rounds=6, seed=41),
    )

    assert result.reference_strike.attacker.name == "Novice"
    assert result.reference_strike.defender.name == "Guard"


def test_team_battle_reports_progress_until_complete() -> None:
    team_one = _team(
        "Team 1",
        _combatant("Team 1 A", SkillRank.FOUR),
    )
    team_two = _team(
        "Team 2",
        _combatant("Team 2 A", SkillRank.THREE),
    )
    updates: list[tuple[int, int]] = []

    simulate_team_battle(
        team_one,
        team_two,
        DuelSimulationConfig(trials=25, max_rounds=5, seed=43),
        progress_callback=lambda completed, total: updates.append((completed, total)),
    )

    assert updates[0] == (0, 25)
    assert updates[-1] == (25, 25)
    assert all(total == 25 for _, total in updates)
    assert updates == sorted(updates)
