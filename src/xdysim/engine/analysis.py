"""Exact analytical probability helpers for skill checks and opposed rolls."""

from __future__ import annotations

from collections import Counter
from fractions import Fraction
from functools import cache
from itertools import product
from math import prod

import numpy as np

from xdysim.engine.models import (
    ALL_SKILL_RANKS,
    DicePool,
    OpposedRollSummary,
    RollDistribution,
    SkillRank,
    StaticCheckSummary,
    all_dice_pools,
    coerce_skill_rank,
)


def _resolve_roll(rolls: tuple[int, ...], dice: tuple[int, ...]) -> int:
    highest = max(rolls)
    bonus = sum(
        1
        for roll, sides in zip(rolls, dice, strict=True)
        if roll == sides and roll < highest
    )
    return highest + bonus


@cache
def distribution_for_rank(rank: SkillRank | int) -> RollDistribution:
    """Return the exact probability mass function for a skill rank."""
    skill_rank = coerce_skill_rank(rank)
    pool = DicePool.for_rank(skill_rank)
    outcomes = product(*(range(1, sides + 1) for sides in pool.dice))
    counts = Counter(_resolve_roll(rolls, pool.dice) for rolls in outcomes)
    denominator = prod(pool.dice)
    pmf = {
        result: Fraction(count, denominator)
        for result, count in sorted(counts.items())
    }
    return RollDistribution(pool=pool, pmf=pmf)


@cache
def distribution_for_rank_with_edge(
    rank: SkillRank | int,
    edge_hindrance: int = 0,
) -> RollDistribution:
    """Return the exact PMF after applying net Edge or Hindrance."""
    if edge_hindrance == 0:
        return distribution_for_rank(rank)

    skill_rank = coerce_skill_rank(rank)
    pool = DicePool.for_rank(skill_rank)
    smaller_dice = pool.dice[:-1]
    largest_die = pool.dice[-1]
    largest_samples = abs(edge_hindrance) + 1

    selected_largest_counts = {
        result: result**largest_samples - (result - 1) ** largest_samples
        for result in range(1, largest_die + 1)
    }
    if edge_hindrance < 0:
        selected_largest_counts = {
            result: (largest_die - result + 1) ** largest_samples
            - (largest_die - result) ** largest_samples
            for result in range(1, largest_die + 1)
        }

    smaller_outcomes = product(*(range(1, sides + 1) for sides in smaller_dice))
    counts: Counter[int] = Counter()
    for smaller_rolls in smaller_outcomes:
        for selected_largest, selected_count in selected_largest_counts.items():
            rolls = (*smaller_rolls, selected_largest)
            counts[_resolve_roll(rolls, pool.dice)] += selected_count

    denominator = prod(smaller_dice) * largest_die**largest_samples
    pmf = {
        result: Fraction(count, denominator)
        for result, count in sorted(counts.items())
    }
    return RollDistribution(pool=pool, pmf=pmf)


@cache
def static_check(
    rank: SkillRank | int,
    dc: int,
    circumstance: int = 0,
    edge_hindrance: int = 0,
) -> StaticCheckSummary:
    """Return exact probabilities for a static check against the given DC."""
    distribution = distribution_for_rank_with_edge(rank, edge_hindrance).shifted(circumstance)
    probability_eq = distribution.probability_of(dc)
    probability_gt = sum(
        (
            probability
            for result, probability in distribution.ordered_pmf
            if result > dc
        ),
        start=Fraction(),
    )
    probability_lte = sum(
        (
            probability
            for result, probability in distribution.ordered_pmf
            if result <= dc
        ),
        start=Fraction(),
    )
    return StaticCheckSummary(
        pool=distribution.pool,
        dc=dc,
        circumstance=circumstance,
        edge_hindrance=edge_hindrance,
        probability_gt=probability_gt,
        probability_eq=probability_eq,
        probability_gte=probability_gt + probability_eq,
        probability_lte=probability_lte,
    )


@cache
def opposed_roll(
    attacker_rank: SkillRank | int,
    defender_rank: SkillRank | int,
    attacker_circumstance: int = 0,
    defender_circumstance: int = 0,
    attacker_edge_hindrance: int = 0,
    defender_edge_hindrance: int = 0,
) -> OpposedRollSummary:
    """Return exact win, tie, and positive-margin metrics for an opposed roll."""
    attacker_distribution = distribution_for_rank_with_edge(
        attacker_rank,
        attacker_edge_hindrance,
    ).shifted(attacker_circumstance)
    defender_distribution = distribution_for_rank_with_edge(
        defender_rank,
        defender_edge_hindrance,
    ).shifted(defender_circumstance)
    probability_attacker_win = Fraction()
    probability_tie = Fraction()
    expected_positive_margin = Fraction()

    for attacker_result, attacker_probability in attacker_distribution.ordered_pmf:
        for defender_result, defender_probability in defender_distribution.ordered_pmf:
            pair_probability = attacker_probability * defender_probability
            if attacker_result > defender_result:
                probability_attacker_win += pair_probability
                expected_positive_margin += (
                    attacker_result - defender_result
                ) * pair_probability
            elif attacker_result == defender_result:
                probability_tie += pair_probability

    return OpposedRollSummary(
        attacker_pool=attacker_distribution.pool,
        defender_pool=defender_distribution.pool,
        attacker_circumstance=attacker_circumstance,
        defender_circumstance=defender_circumstance,
        attacker_edge_hindrance=attacker_edge_hindrance,
        defender_edge_hindrance=defender_edge_hindrance,
        probability_attacker_win=probability_attacker_win,
        probability_tie=probability_tie,
        probability_attacker_lte=Fraction(1, 1) - probability_attacker_win,
        expected_positive_margin=expected_positive_margin,
    )


def opposed_metric_matrices(
    attacker_circumstance: int = 0,
    defender_circumstance: int = 0,
    attacker_edge_hindrance: int = 0,
    defender_edge_hindrance: int = 0,
) -> tuple[list[DicePool], np.ndarray, np.ndarray]:
    """Build all rank-vs-rank win-rate and positive-margin matrices."""
    pools = list(all_dice_pools())
    size = len(pools)
    win_matrix = np.zeros((size, size), dtype=float)
    margin_matrix = np.zeros((size, size), dtype=float)

    for attacker_index, attacker in enumerate(ALL_SKILL_RANKS):
        for defender_index, defender in enumerate(ALL_SKILL_RANKS):
            summary = opposed_roll(
                attacker,
                defender,
                attacker_circumstance=attacker_circumstance,
                defender_circumstance=defender_circumstance,
                attacker_edge_hindrance=attacker_edge_hindrance,
                defender_edge_hindrance=defender_edge_hindrance,
            )
            win_matrix[attacker_index, defender_index] = float(summary.probability_attacker_win)
            margin_matrix[attacker_index, defender_index] = float(summary.expected_positive_margin)

    return pools, win_matrix, margin_matrix
