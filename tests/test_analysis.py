from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import given, settings
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
    distribution_for_rank_with_edge,
    opposed_metric_matrices,
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


@pytest.mark.parametrize("rank", ALL_SKILL_RANKS)
@pytest.mark.parametrize("modifier", [-40, -3, 0, 3, 40])
def test_shifted_distribution_preserves_probability_mass(
    rank: SkillRank,
    modifier: int,
) -> None:
    distribution = distribution_for_rank(rank)
    shifted = distribution.shifted(modifier)

    assert sum(shifted.pmf.values(), start=Fraction()) == Fraction(1, 1)
    assert shifted.ordered_pmf == tuple(
        (result + modifier, probability)
        for result, probability in distribution.ordered_pmf
    )


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


def test_edge_zero_distribution_matches_base_distribution() -> None:
    for rank in ALL_SKILL_RANKS:
        assert distribution_for_rank_with_edge(rank).pmf == distribution_for_rank(rank).pmf
        assert distribution_for_rank_with_edge(rank, edge_hindrance=0).pmf == (
            distribution_for_rank(rank).pmf
        )


def test_rank_one_edge_distribution_matches_known_profile() -> None:
    distribution = distribution_for_rank_with_edge(SkillRank.ONE, edge_hindrance=1)

    assert distribution.pmf == {
        1: Fraction(1, 16),
        2: Fraction(3, 16),
        3: Fraction(5, 16),
        4: Fraction(7, 16),
    }


def test_rank_one_hindrance_distribution_matches_known_profile() -> None:
    distribution = distribution_for_rank_with_edge(SkillRank.ONE, edge_hindrance=-1)

    assert distribution.pmf == {
        1: Fraction(7, 16),
        2: Fraction(5, 16),
        3: Fraction(3, 16),
        4: Fraction(1, 16),
    }


@pytest.mark.parametrize(
    ("edge_hindrance", "expected_pmf"),
    [
        (
            1,
            {
                1: Fraction(1, 144),
                2: Fraction(7, 144),
                3: Fraction(19, 144),
                4: Fraction(37, 144),
                5: Fraction(3, 16),
                6: Fraction(7, 24),
                7: Fraction(11, 144),
            },
        ),
        (
            -1,
            {
                1: Fraction(11, 144),
                2: Fraction(29, 144),
                3: Fraction(41, 144),
                4: Fraction(47, 144),
                5: Fraction(1, 16),
                6: Fraction(1, 24),
                7: Fraction(1, 144),
            },
        ),
    ],
)
def test_rank_two_edge_hindrance_distribution_matches_known_profile(
    edge_hindrance: int,
    expected_pmf: dict[int, Fraction],
) -> None:
    distribution = distribution_for_rank_with_edge(
        SkillRank.TWO,
        edge_hindrance=edge_hindrance,
    )

    assert distribution.pmf == expected_pmf


@pytest.mark.parametrize("edge_hindrance", [-2, -1, 0, 1, 2])
def test_edge_hindrance_distribution_probability_mass_sums_to_one(
    edge_hindrance: int,
) -> None:
    distribution = distribution_for_rank_with_edge(
        SkillRank.THREE,
        edge_hindrance=edge_hindrance,
    )

    assert sum(distribution.pmf.values(), start=Fraction()) == Fraction(1, 1)


def test_static_check_applies_positive_circumstance() -> None:
    summary = static_check(SkillRank.TWO, 4, circumstance=1)

    assert summary.circumstance == 1
    assert summary.probability_gt == Fraction(15, 24)
    assert summary.probability_eq == Fraction(5, 24)
    assert summary.probability_gte == Fraction(20, 24)
    assert summary.probability_lte == Fraction(9, 24)


def test_static_check_applies_negative_circumstance() -> None:
    summary = static_check(SkillRank.TWO, 4, circumstance=-2)

    assert summary.circumstance == -2
    assert summary.probability_gt == Fraction(1, 24)
    assert summary.probability_eq == Fraction(4, 24)
    assert summary.probability_gte == Fraction(5, 24)
    assert summary.probability_lte == Fraction(23, 24)


def test_static_check_applies_edge() -> None:
    summary = static_check(SkillRank.ONE, 2, edge_hindrance=1)

    assert summary.edge_hindrance == 1
    assert summary.probability_gt == Fraction(3, 4)
    assert summary.probability_eq == Fraction(3, 16)
    assert summary.probability_gte == Fraction(15, 16)
    assert summary.probability_lte == Fraction(1, 4)


def test_static_check_applies_hindrance() -> None:
    summary = static_check(SkillRank.ONE, 2, edge_hindrance=-1)

    assert summary.edge_hindrance == -1
    assert summary.probability_gt == Fraction(1, 4)
    assert summary.probability_eq == Fraction(5, 16)
    assert summary.probability_gte == Fraction(9, 16)
    assert summary.probability_lte == Fraction(3, 4)


def test_static_check_applies_circumstance_after_edge() -> None:
    summary = static_check(SkillRank.ONE, 2, circumstance=1, edge_hindrance=1)

    assert summary.circumstance == 1
    assert summary.edge_hindrance == 1
    assert summary.probability_gt == Fraction(15, 16)
    assert summary.probability_eq == Fraction(1, 16)
    assert summary.probability_lte == Fraction(1, 16)


@pytest.mark.parametrize("rank", ALL_SKILL_RANKS)
@pytest.mark.parametrize("circumstance", [-3, 0, 3])
def test_static_check_internal_relationships(rank: SkillRank, circumstance: int) -> None:
    for dc in range(0, 26):
        summary = static_check(rank, dc, circumstance=circumstance)
        distribution = distribution_for_rank(rank).shifted(circumstance)
        expected_lte = sum(
            (
                probability
                for result, probability in distribution.ordered_pmf
                if result <= dc
            ),
            start=Fraction(),
        )
        assert summary.circumstance == circumstance
        assert summary.probability_gt + summary.probability_eq == summary.probability_gte
        assert summary.probability_lte == expected_lte
        assert summary.probability_gt + summary.probability_lte == Fraction(1, 1)
        assert Fraction() <= summary.probability_gt <= Fraction(1, 1)
        assert Fraction() <= summary.probability_eq <= Fraction(1, 1)
        assert Fraction() <= summary.probability_lte <= Fraction(1, 1)


@given(rank=RANK_STRATEGY, dc=st.integers(min_value=0, max_value=24))
def test_static_check_probability_is_monotonic(rank: SkillRank, dc: int) -> None:
    current = static_check(rank, dc)
    next_summary = static_check(rank, dc + 1)
    assert current.probability_gt >= next_summary.probability_gt
    assert current.probability_lte <= next_summary.probability_lte


@given(
    rank=RANK_STRATEGY,
    dc=st.integers(min_value=0, max_value=24),
    circumstance=st.integers(min_value=-40, max_value=39),
)
def test_static_check_probability_is_monotonic_by_circumstance(
    rank: SkillRank,
    dc: int,
    circumstance: int,
) -> None:
    current = static_check(rank, dc, circumstance=circumstance)
    increased = static_check(rank, dc, circumstance=circumstance + 1)
    assert current.probability_gt <= increased.probability_gt
    assert current.probability_lte >= increased.probability_lte


@pytest.mark.parametrize("dc", range(0, 8))
def test_static_check_probability_is_monotonic_by_edge_hindrance(dc: int) -> None:
    hindrance = static_check(SkillRank.TWO, dc, edge_hindrance=-1)
    normal = static_check(SkillRank.TWO, dc)
    edge = static_check(SkillRank.TWO, dc, edge_hindrance=1)

    assert hindrance.probability_gt <= normal.probability_gt <= edge.probability_gt
    assert hindrance.probability_lte >= normal.probability_lte >= edge.probability_lte


@given(attacker=RANK_STRATEGY, defender=RANK_STRATEGY)
def test_opposed_symmetry_relationship(attacker: SkillRank, defender: SkillRank) -> None:
    forward = opposed_roll(attacker, defender)
    reverse = opposed_roll(defender, attacker)
    assert forward.probability_tie == reverse.probability_tie
    assert forward.probability_attacker_lte == (
        Fraction(1, 1) - forward.probability_attacker_win
    )
    assert (
        forward.probability_attacker_win
        + reverse.probability_attacker_win
        + forward.probability_tie
        == Fraction(1, 1)
    )


@pytest.mark.parametrize(
    (
        "attacker_circumstance",
        "defender_circumstance",
        "expected_win",
        "expected_tie",
        "expected_margin",
    ),
    [
        (1, 0, Fraction(343, 576), Fraction(5, 32), Fraction(827, 576)),
        (0, 1, Fraction(143, 576), Fraction(5, 32), Fraction(251, 576)),
        (2, -1, Fraction(505, 576), Fraction(43, 576), Fraction(1765, 576)),
    ],
)
def test_opposed_roll_applies_circumstances(
    attacker_circumstance: int,
    defender_circumstance: int,
    expected_win: Fraction,
    expected_tie: Fraction,
    expected_margin: Fraction,
) -> None:
    summary = opposed_roll(
        SkillRank.TWO,
        SkillRank.TWO,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
    )

    assert summary.attacker_circumstance == attacker_circumstance
    assert summary.defender_circumstance == defender_circumstance
    assert summary.probability_attacker_win == expected_win
    assert summary.probability_tie == expected_tie
    assert summary.probability_attacker_lte == Fraction(1, 1) - expected_win
    assert summary.expected_positive_margin == expected_margin


@pytest.mark.parametrize(
    (
        "attacker_edge_hindrance",
        "defender_edge_hindrance",
        "expected_win",
        "expected_tie",
        "expected_lte",
        "expected_margin",
    ),
    [
        (1, 0, Fraction(211, 384), Fraction(53, 288), Fraction(173, 384), Fraction(535, 432)),
        (0, 1, Fraction(307, 1152), Fraction(53, 288), Fraction(845, 1152), Fraction(211, 432)),
        (
            1,
            -1,
            Fraction(14617, 20736),
            Fraction(1619, 10368),
            Fraction(6119, 20736),
            Fraction(8891, 5184),
        ),
    ],
)
def test_opposed_roll_applies_edge_hindrance(
    attacker_edge_hindrance: int,
    defender_edge_hindrance: int,
    expected_win: Fraction,
    expected_tie: Fraction,
    expected_lte: Fraction,
    expected_margin: Fraction,
) -> None:
    summary = opposed_roll(
        SkillRank.TWO,
        SkillRank.TWO,
        attacker_edge_hindrance=attacker_edge_hindrance,
        defender_edge_hindrance=defender_edge_hindrance,
    )

    assert summary.attacker_edge_hindrance == attacker_edge_hindrance
    assert summary.defender_edge_hindrance == defender_edge_hindrance
    assert summary.probability_attacker_win == expected_win
    assert summary.probability_tie == expected_tie
    assert summary.probability_attacker_lte == expected_lte
    assert summary.probability_attacker_lte == Fraction(1, 1) - expected_win
    assert summary.expected_positive_margin == expected_margin


@given(
    attacker=RANK_STRATEGY,
    defender=RANK_STRATEGY,
    attacker_circumstance=st.integers(min_value=-5, max_value=5),
    defender_circumstance=st.integers(min_value=-5, max_value=5),
)
def test_opposed_symmetry_relationship_with_circumstances(
    attacker: SkillRank,
    defender: SkillRank,
    attacker_circumstance: int,
    defender_circumstance: int,
) -> None:
    forward = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
    )
    reverse = opposed_roll(
        defender,
        attacker,
        attacker_circumstance=defender_circumstance,
        defender_circumstance=attacker_circumstance,
    )

    assert forward.probability_tie == reverse.probability_tie
    assert forward.probability_attacker_lte == (
        Fraction(1, 1) - forward.probability_attacker_win
    )
    assert (
        forward.probability_attacker_win
        + reverse.probability_attacker_win
        + forward.probability_tie
        == Fraction(1, 1)
    )


@settings(deadline=None)
@given(
    attacker=RANK_STRATEGY,
    defender=RANK_STRATEGY,
    attacker_circumstance=st.integers(min_value=-3, max_value=3),
    defender_circumstance=st.integers(min_value=-3, max_value=3),
    attacker_edge_hindrance=st.integers(min_value=-1, max_value=1),
    defender_edge_hindrance=st.integers(min_value=-1, max_value=1),
)
def test_opposed_symmetry_relationship_with_modifiers(
    attacker: SkillRank,
    defender: SkillRank,
    attacker_circumstance: int,
    defender_circumstance: int,
    attacker_edge_hindrance: int,
    defender_edge_hindrance: int,
) -> None:
    forward = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
        attacker_edge_hindrance=attacker_edge_hindrance,
        defender_edge_hindrance=defender_edge_hindrance,
    )
    reverse = opposed_roll(
        defender,
        attacker,
        attacker_circumstance=defender_circumstance,
        defender_circumstance=attacker_circumstance,
        attacker_edge_hindrance=defender_edge_hindrance,
        defender_edge_hindrance=attacker_edge_hindrance,
    )

    assert forward.probability_tie == reverse.probability_tie
    assert forward.probability_attacker_lte == (
        Fraction(1, 1) - forward.probability_attacker_win
    )
    assert (
        forward.probability_attacker_win
        + reverse.probability_attacker_win
        + forward.probability_tie
        == Fraction(1, 1)
    )


@given(
    attacker=RANK_STRATEGY,
    defender=RANK_STRATEGY,
    attacker_circumstance=st.integers(min_value=-5, max_value=4),
    defender_circumstance=st.integers(min_value=-5, max_value=5),
)
def test_opposed_roll_improves_with_attacker_circumstance(
    attacker: SkillRank,
    defender: SkillRank,
    attacker_circumstance: int,
    defender_circumstance: int,
) -> None:
    current = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
    )
    increased = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance + 1,
        defender_circumstance=defender_circumstance,
    )

    assert current.probability_attacker_win <= increased.probability_attacker_win
    assert current.expected_positive_margin <= increased.expected_positive_margin


@settings(deadline=None)
@given(
    attacker=RANK_STRATEGY,
    defender=RANK_STRATEGY,
    attacker_circumstance=st.integers(min_value=-3, max_value=3),
    defender_circumstance=st.integers(min_value=-3, max_value=3),
    attacker_edge_hindrance=st.integers(min_value=-1, max_value=0),
    defender_edge_hindrance=st.integers(min_value=-1, max_value=1),
)
def test_opposed_roll_improves_with_attacker_edge_hindrance(
    attacker: SkillRank,
    defender: SkillRank,
    attacker_circumstance: int,
    defender_circumstance: int,
    attacker_edge_hindrance: int,
    defender_edge_hindrance: int,
) -> None:
    current = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
        attacker_edge_hindrance=attacker_edge_hindrance,
        defender_edge_hindrance=defender_edge_hindrance,
    )
    increased = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
        attacker_edge_hindrance=attacker_edge_hindrance + 1,
        defender_edge_hindrance=defender_edge_hindrance,
    )

    assert current.probability_attacker_win <= increased.probability_attacker_win
    assert current.expected_positive_margin <= increased.expected_positive_margin


@given(
    attacker=RANK_STRATEGY,
    defender=RANK_STRATEGY,
    attacker_circumstance=st.integers(min_value=-5, max_value=5),
    defender_circumstance=st.integers(min_value=-5, max_value=4),
)
def test_opposed_roll_declines_with_defender_circumstance(
    attacker: SkillRank,
    defender: SkillRank,
    attacker_circumstance: int,
    defender_circumstance: int,
) -> None:
    current = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
    )
    increased = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance + 1,
    )

    assert current.probability_attacker_win >= increased.probability_attacker_win
    assert current.expected_positive_margin >= increased.expected_positive_margin


@settings(deadline=None)
@given(
    attacker=RANK_STRATEGY,
    defender=RANK_STRATEGY,
    attacker_circumstance=st.integers(min_value=-3, max_value=3),
    defender_circumstance=st.integers(min_value=-3, max_value=3),
    attacker_edge_hindrance=st.integers(min_value=-1, max_value=1),
    defender_edge_hindrance=st.integers(min_value=-1, max_value=0),
)
def test_opposed_roll_declines_with_defender_edge_hindrance(
    attacker: SkillRank,
    defender: SkillRank,
    attacker_circumstance: int,
    defender_circumstance: int,
    attacker_edge_hindrance: int,
    defender_edge_hindrance: int,
) -> None:
    current = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
        attacker_edge_hindrance=attacker_edge_hindrance,
        defender_edge_hindrance=defender_edge_hindrance,
    )
    increased = opposed_roll(
        attacker,
        defender,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
        attacker_edge_hindrance=attacker_edge_hindrance,
        defender_edge_hindrance=defender_edge_hindrance + 1,
    )

    assert current.probability_attacker_win >= increased.probability_attacker_win
    assert current.expected_positive_margin >= increased.expected_positive_margin


def test_opposed_metric_matrices_apply_circumstances() -> None:
    _pools, win_matrix, margin_matrix = opposed_metric_matrices(
        attacker_circumstance=1,
        defender_circumstance=0,
    )
    summary = opposed_roll(
        SkillRank.TWO,
        SkillRank.TWO,
        attacker_circumstance=1,
        defender_circumstance=0,
    )

    assert win_matrix[1, 1] == pytest.approx(float(summary.probability_attacker_win))
    assert margin_matrix[1, 1] == pytest.approx(float(summary.expected_positive_margin))


def test_opposed_metric_matrices_apply_edge_hindrance_and_circumstances() -> None:
    _pools, win_matrix, margin_matrix = opposed_metric_matrices(
        attacker_circumstance=1,
        defender_circumstance=-1,
        attacker_edge_hindrance=1,
        defender_edge_hindrance=-1,
    )
    summary = opposed_roll(
        SkillRank.TWO,
        SkillRank.TWO,
        attacker_circumstance=1,
        defender_circumstance=-1,
        attacker_edge_hindrance=1,
        defender_edge_hindrance=-1,
    )

    assert win_matrix[1, 1] == pytest.approx(float(summary.probability_attacker_win))
    assert margin_matrix[1, 1] == pytest.approx(float(summary.expected_positive_margin))


@pytest.mark.parametrize("rank", ALL_SKILL_RANKS)
def test_defender_wins_ties_for_equal_ranks(rank: SkillRank) -> None:
    summary = opposed_roll(rank, rank)
    assert summary.probability_tie > Fraction()
    assert summary.probability_attacker_win == (Fraction(1, 1) - summary.probability_tie) / 2
    assert summary.probability_attacker_lte == (
        Fraction(1, 1) - summary.probability_attacker_win
    )


def test_minor_injury_upgrades_when_minor_track_is_full() -> None:
    combatant = Combatant(
        name="Guardian",
        combat=CombatProfile(
            attack_skill_rank=SkillRank.THREE,
            defense_skill_rank=SkillRank.THREE,
            initiative_skill_rank=SkillRank.THREE,
        ),
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
        combat=CombatProfile(
            attack_skill_rank=SkillRank.ONE,
            defense_skill_rank=SkillRank.ONE,
            initiative_skill_rank=SkillRank.ONE,
        ),
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


def test_static_lte_matches_reference_gt_complement() -> None:
    reference_table = REFERENCE_DATA["static_gt"]
    for attacker_label, dc_values in reference_table.items():
        rank = RANK_BY_LABEL[attacker_label]
        for dc_text, reference_gt in dc_values.items():
            summary = static_check(rank, int(dc_text))
            assert float(summary.probability_lte) == pytest.approx(
                1.0 - reference_gt,
                abs=1e-10,
            )
