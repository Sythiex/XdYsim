from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from xdysim.engine import (
    ALL_SKILL_RANKS,
    Armor,
    Combatant,
    CombatProfile,
    CombatState,
    InjuryTrack,
    all_dice_pools,
    apply_injury,
    distribution_for_rank,
    opposed_roll,
    resolve_martial_attack,
    static_check,
)
from xdysim.engine.combat import InjurySeverity
from xdysim.engine.models import SkillRank

REFERENCE_DATA = json.loads(
    (Path(__file__).parent / "data" / "spreadsheet_reference.json").read_text()
)
RANK_BY_LABEL = {pool.label: pool.rank for pool in all_dice_pools()}
RANK_STRATEGY = st.integers(min_value=1, max_value=6).map(SkillRank)


def test_pool_catalog_matches_expected_labels() -> None:
    assert [pool.label for pool in all_dice_pools()] == REFERENCE_DATA["labels"]


@pytest.mark.parametrize("rank", ALL_SKILL_RANKS)
def test_distribution_probability_mass_sums_to_one(rank: SkillRank) -> None:
    distribution = distribution_for_rank(rank)
    assert sum(distribution.pmf.values(), start=Fraction()) == Fraction(1, 1)


def test_rank_two_distribution_matches_known_profile() -> None:
    distribution = distribution_for_rank(SkillRank.TWO)
    assert distribution.pmf == {
        1: Fraction(1, 24),
        2: Fraction(3, 24),
        3: Fraction(5, 24),
        4: Fraction(7, 24),
        5: Fraction(3, 24),
        6: Fraction(4, 24),
        7: Fraction(1, 24),
    }


@pytest.mark.parametrize("rank", ALL_SKILL_RANKS)
def test_static_check_internal_relationships(rank: SkillRank) -> None:
    for dc in range(0, 26):
        summary = static_check(rank, dc)
        assert summary.probability_gt + summary.probability_eq == summary.probability_gte
        assert Fraction() <= summary.probability_gt <= Fraction(1, 1)
        assert Fraction() <= summary.probability_eq <= Fraction(1, 1)


@given(rank=RANK_STRATEGY, dc=st.integers(min_value=0, max_value=24))
def test_static_check_probability_is_monotonic(rank: SkillRank, dc: int) -> None:
    current = static_check(rank, dc)
    next_summary = static_check(rank, dc + 1)
    assert current.probability_gt >= next_summary.probability_gt


@given(attacker=RANK_STRATEGY, defender=RANK_STRATEGY)
def test_opposed_symmetry_relationship(attacker: SkillRank, defender: SkillRank) -> None:
    forward = opposed_roll(attacker, defender)
    reverse = opposed_roll(defender, attacker)
    assert forward.probability_tie == reverse.probability_tie
    assert (
        forward.probability_attacker_win
        + reverse.probability_attacker_win
        + forward.probability_tie
        == Fraction(1, 1)
    )


@pytest.mark.parametrize("rank", ALL_SKILL_RANKS)
def test_defender_wins_ties_for_equal_ranks(rank: SkillRank) -> None:
    summary = opposed_roll(rank, rank)
    assert summary.probability_tie > Fraction()
    assert summary.probability_attacker_win == (Fraction(1, 1) - summary.probability_tie) / 2


def test_minor_injury_upgrades_when_minor_track_is_full() -> None:
    combatant = Combatant(
        name="Guardian",
        combat=CombatProfile(skill_rank=SkillRank.THREE),
        injury_track=InjuryTrack(minor_capacity=0, major_capacity=2),
    )
    state = CombatState(combatant=combatant)
    updated_state, severity = apply_injury(state, remaining_damage=2)
    assert severity is InjurySeverity.MAJOR
    assert updated_state.major_injuries == 1
    assert updated_state.minor_injuries == 0


def test_major_injury_overflow_causes_unconsciousness() -> None:
    defender = Combatant(
        name="Target",
        combat=CombatProfile(skill_rank=SkillRank.ONE),
        armor=Armor(rating=1),
        injury_track=InjuryTrack(minor_capacity=1, major_capacity=1),
    )
    initial_state = CombatState(combatant=defender, major_injuries=1)
    outcome = resolve_martial_attack(
        attacker_result=9,
        defender_result=4,
        defender_state=initial_state,
    )
    assert outcome.hit is True
    assert outcome.damage_after_armor == 4
    assert outcome.injury_severity is InjurySeverity.MAJOR
    assert outcome.target_state.unconscious is True
    assert outcome.target_state.bleeding_out is True


@pytest.mark.parametrize(
    ("table_name", "metric_name"),
    [
        ("opposed_win", "probability_attacker_win"),
        ("opposed_expected_margin", "expected_positive_margin"),
    ],
)
def test_opposed_reference_tables(table_name: str, metric_name: str) -> None:
    reference_table = REFERENCE_DATA[table_name]
    for attacker_label, row in reference_table.items():
        attacker_rank = RANK_BY_LABEL[attacker_label]
        for defender_label, reference_value in row.items():
            defender_rank = RANK_BY_LABEL[defender_label]
            summary = opposed_roll(attacker_rank, defender_rank)
            actual = float(getattr(summary, metric_name))
            assert actual == pytest.approx(reference_value, abs=1e-9)


@pytest.mark.parametrize(
    ("table_name", "metric_name"),
    [
        ("static_gt", "probability_gt"),
        ("static_eq", "probability_eq"),
    ],
)
def test_static_reference_tables(table_name: str, metric_name: str) -> None:
    reference_table = REFERENCE_DATA[table_name]
    for attacker_label, dc_values in reference_table.items():
        rank = RANK_BY_LABEL[attacker_label]
        for dc_text, reference_value in dc_values.items():
            summary = static_check(rank, int(dc_text))
            actual = float(getattr(summary, metric_name))
            assert actual == pytest.approx(reference_value, abs=1e-10)
