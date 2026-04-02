from __future__ import annotations

from fractions import Fraction

import pytest

from xdysim.engine import (
    Armor,
    Combatant,
    CombatProfile,
    DuelSimulationConfig,
    InjuryTrack,
    SkillRank,
    analyze_opening_attack,
    opposed_roll,
    simulate_duel,
)


def _combatant(
    name: str,
    attack_rank: SkillRank,
    *,
    defense_rank: SkillRank | None = None,
    armor: int = 0,
    minor_capacity: int = 2,
    major_capacity: int = 2,
) -> Combatant:
    return Combatant(
        name=name,
        combat=CombatProfile(
            attack_skill_rank=attack_rank,
            defense_skill_rank=defense_rank or attack_rank,
        ),
        armor=Armor(rating=armor),
        injury_track=InjuryTrack(
            minor_capacity=minor_capacity,
            major_capacity=major_capacity,
        ),
    )


def test_opening_attack_matches_exact_opposed_values_without_armor() -> None:
    attacker = _combatant("Attacker", SkillRank.FOUR)
    defender = _combatant("Defender", SkillRank.THREE)

    summary = analyze_opening_attack(attacker, defender)
    opposed_summary = opposed_roll(
        attacker.combat.attack_skill_rank,
        defender.combat.defense_skill_rank,
    )

    assert summary.hit_probability == opposed_summary.probability_attacker_win
    assert summary.tie_probability == opposed_summary.probability_tie
    assert summary.expected_incoming_damage == opposed_summary.expected_positive_margin
    assert summary.expected_damage_after_armor == opposed_summary.expected_positive_margin
    assert (
        summary.probability_no_injury
        + summary.probability_minor_injury
        + summary.probability_major_injury
        + summary.probability_unconscious
        == Fraction(1, 1)
    )


def test_opening_attack_respects_armor() -> None:
    attacker = _combatant("Attacker", SkillRank.FIVE)
    unarmored = _combatant("Unarmored", SkillRank.THREE, armor=0)
    armored = _combatant("Armored", SkillRank.THREE, armor=3)

    unarmored_summary = analyze_opening_attack(attacker, unarmored)
    armored_summary = analyze_opening_attack(attacker, armored)

    assert (
        armored_summary.expected_damage_after_armor
        < unarmored_summary.expected_damage_after_armor
    )
    assert armored_summary.probability_no_injury > unarmored_summary.probability_no_injury


def test_better_defense_skill_reduces_opening_attack_success() -> None:
    attacker = _combatant("Attacker", SkillRank.FOUR, defense_rank=SkillRank.THREE)
    weak_defender = _combatant("Weak Defender", SkillRank.THREE, defense_rank=SkillRank.TWO)
    strong_defender = _combatant("Strong Defender", SkillRank.THREE, defense_rank=SkillRank.FIVE)

    weak_summary = analyze_opening_attack(attacker, weak_defender)
    strong_summary = analyze_opening_attack(attacker, strong_defender)

    assert weak_summary.hit_probability > strong_summary.hit_probability
    assert weak_summary.expected_incoming_damage > strong_summary.expected_incoming_damage


def test_duel_simulation_is_seeded_and_repeatable() -> None:
    attacker = _combatant("Attacker", SkillRank.FOUR, armor=1)
    defender = _combatant("Defender", SkillRank.THREE, armor=1)
    config = DuelSimulationConfig(trials=2_000, max_rounds=8, seed=11)

    first = simulate_duel(attacker, defender, config)
    second = simulate_duel(attacker, defender, config)

    assert first.model_dump() == second.model_dump()


def test_duel_simulation_outputs_well_formed_probabilities() -> None:
    attacker = _combatant("Attacker", SkillRank.FOUR, armor=1)
    defender = _combatant("Defender", SkillRank.THREE, armor=1)
    result = simulate_duel(
        attacker,
        defender,
        DuelSimulationConfig(trials=2_500, max_rounds=8, seed=5),
    )

    assert len(result.round_summaries) == 8
    assert (
        result.attacker_win_rate + result.defender_win_rate + result.unresolved_rate
        == pytest.approx(1.0)
    )

    previous_defender_unconscious = 0.0
    previous_attacker_unconscious = 0.0
    for round_summary in result.round_summaries:
        assert round_summary.defender.probability_unconscious >= previous_defender_unconscious
        assert round_summary.attacker.probability_unconscious >= previous_attacker_unconscious
        assert (
            round_summary.defender.probability_any_major_injury
            >= round_summary.defender.probability_unconscious
        )
        previous_defender_unconscious = round_summary.defender.probability_unconscious
        previous_attacker_unconscious = round_summary.attacker.probability_unconscious


def test_stronger_combatant_wins_most_simulated_duels() -> None:
    attacker = _combatant("Elite", SkillRank.SIX, armor=2)
    defender = _combatant("Novice", SkillRank.ONE, armor=0)
    result = simulate_duel(
        attacker,
        defender,
        DuelSimulationConfig(trials=1_500, max_rounds=8, seed=17),
    )

    assert result.attacker_win_rate > 0.9
    assert result.attacker_win_rate > result.defender_win_rate
    assert result.average_rounds_to_resolution is not None
