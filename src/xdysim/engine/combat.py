"""Combat resolution and simulation helpers built on the analytical engine."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from functools import cache

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from xdysim.engine.analysis import distribution_for_rank, opposed_roll
from xdysim.engine.models import Combatant, SkillRank, coerce_skill_rank


class InjurySeverity(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"


class CombatState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    combatant: Combatant
    minor_injuries: int = Field(default=0, ge=0)
    major_injuries: int = Field(default=0, ge=0)
    unconscious: bool = False
    bleeding_out: bool = False


class StrikeOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hit: bool
    incoming_damage: int = Field(default=0, ge=0)
    damage_after_armor: int = Field(default=0, ge=0)
    injury_severity: InjurySeverity = InjurySeverity.NONE
    target_state: CombatState


class AttackResolutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attacker: Combatant
    defender: Combatant
    hit_probability: Fraction
    tie_probability: Fraction
    expected_incoming_damage: Fraction
    expected_damage_after_armor: Fraction
    probability_no_injury: Fraction
    probability_minor_injury: Fraction
    probability_major_injury: Fraction
    probability_unconscious: Fraction

    @model_validator(mode="after")
    def validate_probability_total(self) -> AttackResolutionSummary:
        total = (
            self.probability_no_injury
            + self.probability_minor_injury
            + self.probability_major_injury
            + self.probability_unconscious
        )
        if total != Fraction(1, 1):
            msg = f"exclusive attack outcomes must sum to 1, got {total}"
            raise ValueError(msg)
        return self


class CombatantRoundSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    probability_any_minor_injury: float = Field(ge=0.0, le=1.0)
    probability_any_major_injury: float = Field(ge=0.0, le=1.0)
    probability_unconscious: float = Field(ge=0.0, le=1.0)
    average_minor_injuries: float = Field(ge=0.0)
    average_major_injuries: float = Field(ge=0.0)


class DuelRoundSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    round_number: int = Field(ge=1)
    attacker: CombatantRoundSummary
    defender: CombatantRoundSummary


class DuelSimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trials: int = Field(default=5000, ge=1)
    max_rounds: int = Field(default=20, ge=1)
    seed: int | None = None


class DuelSimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attacker: Combatant
    defender: Combatant
    config: DuelSimulationConfig
    opening_attack: AttackResolutionSummary
    attacker_win_rate: float = Field(ge=0.0, le=1.0)
    defender_win_rate: float = Field(ge=0.0, le=1.0)
    unresolved_rate: float = Field(ge=0.0, le=1.0)
    average_rounds_to_resolution: float | None = Field(default=None, ge=0.0)
    round_summaries: tuple[DuelRoundSummary, ...]

    def defender_unconscious_by_round(self, round_number: int) -> float:
        return self.round_summaries[round_number - 1].defender.probability_unconscious

    def attacker_unconscious_by_round(self, round_number: int) -> float:
        return self.round_summaries[round_number - 1].attacker.probability_unconscious


class CombatTeam(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    combatants: tuple[Combatant, ...]

    @model_validator(mode="after")
    def validate_non_empty(self) -> CombatTeam:
        if not self.combatants:
            msg = "combat teams must contain at least one combatant"
            raise ValueError(msg)
        return self


class TeamRoundSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    probability_team_defeated: float = Field(ge=0.0, le=1.0)
    average_unconscious_combatants: float = Field(ge=0.0)
    average_minor_injuries: float = Field(ge=0.0)
    average_major_injuries: float = Field(ge=0.0)


class TeamBattleRoundSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    round_number: int = Field(ge=1)
    team_one: TeamRoundSummary
    team_two: TeamRoundSummary


class TeamBattleSimulationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    team_one: CombatTeam
    team_two: CombatTeam
    config: DuelSimulationConfig
    reference_strike: AttackResolutionSummary
    team_one_win_rate: float = Field(ge=0.0, le=1.0)
    team_two_win_rate: float = Field(ge=0.0, le=1.0)
    unresolved_rate: float = Field(ge=0.0, le=1.0)
    average_rounds_to_resolution: float | None = Field(default=None, ge=0.0)
    round_summaries: tuple[TeamBattleRoundSummary, ...]

    def team_two_defeated_by_round(self, round_number: int) -> float:
        return self.round_summaries[round_number - 1].team_two.probability_team_defeated

    def team_one_defeated_by_round(self, round_number: int) -> float:
        return self.round_summaries[round_number - 1].team_one.probability_team_defeated


@dataclass(frozen=True)
class _InitiativeEntry:
    team_number: int
    combatant_index: int
    initiative_result: int
    initiative_rank: SkillRank
    random_tiebreaker: float


def classify_injury(remaining_damage: int) -> InjurySeverity:
    """Classify post-armor damage into the game's injury severity bands."""
    if remaining_damage <= 0:
        return InjurySeverity.NONE
    if remaining_damage <= 2:
        return InjurySeverity.MINOR
    return InjurySeverity.MAJOR


def fresh_combat_state(combatant: Combatant) -> CombatState:
    """Create a fresh combat state for a combatant at the start of a battle."""
    return CombatState(combatant=combatant)


def apply_injury(state: CombatState, remaining_damage: int) -> tuple[CombatState, InjurySeverity]:
    """Apply post-armor damage to a combat state and return the updated state."""
    severity = classify_injury(remaining_damage)
    if severity is InjurySeverity.NONE:
        return state, severity

    minor_injuries = state.minor_injuries
    major_injuries = state.major_injuries

    if severity is InjurySeverity.MINOR:
        if minor_injuries >= state.combatant.injury_track.minor_capacity:
            severity = InjurySeverity.MAJOR
        else:
            minor_injuries += 1

    if severity is InjurySeverity.MAJOR:
        major_injuries += 1

    unconscious = major_injuries > state.combatant.injury_track.major_capacity
    updated_state = state.model_copy(
        update={
            "minor_injuries": minor_injuries,
            "major_injuries": major_injuries,
            "unconscious": unconscious,
            "bleeding_out": unconscious,
        }
    )
    return updated_state, severity


def resolve_martial_attack(
    attacker_result: int,
    defender_result: int,
    defender_state: CombatState,
) -> StrikeOutcome:
    """Resolve one opposed martial attack into damage and injury outcomes."""
    if attacker_result <= defender_result:
        return StrikeOutcome(hit=False, target_state=defender_state)

    incoming_damage = attacker_result - defender_result
    damage_after_armor = max(incoming_damage - defender_state.combatant.armor.rating, 0)
    target_state, injury_severity = apply_injury(defender_state, damage_after_armor)
    return StrikeOutcome(
        hit=True,
        incoming_damage=incoming_damage,
        damage_after_armor=damage_after_armor,
        injury_severity=injury_severity,
        target_state=target_state,
    )


def analyze_opening_attack(attacker: Combatant, defender: Combatant) -> AttackResolutionSummary:
    """Compute exact one-attack outcome probabilities for a combatant pair."""
    opposed_summary = opposed_roll(
        attacker.combat.attack_skill_rank,
        defender.combat.defense_skill_rank,
    )
    defender_state = fresh_combat_state(defender)

    expected_damage_after_armor = Fraction()
    probability_no_injury = Fraction()
    probability_minor_injury = Fraction()
    probability_major_injury = Fraction()
    probability_unconscious = Fraction()

    attacker_distribution = distribution_for_rank(attacker.combat.attack_skill_rank)
    defender_distribution = distribution_for_rank(defender.combat.defense_skill_rank)

    for attacker_result, attacker_probability in attacker_distribution.ordered_pmf:
        for defender_result, defender_probability in defender_distribution.ordered_pmf:
            pair_probability = attacker_probability * defender_probability
            outcome = resolve_martial_attack(attacker_result, defender_result, defender_state)
            expected_damage_after_armor += outcome.damage_after_armor * pair_probability

            if outcome.target_state.unconscious:
                probability_unconscious += pair_probability
            elif outcome.injury_severity is InjurySeverity.MAJOR:
                probability_major_injury += pair_probability
            elif outcome.injury_severity is InjurySeverity.MINOR:
                probability_minor_injury += pair_probability
            else:
                probability_no_injury += pair_probability

    return AttackResolutionSummary(
        attacker=attacker,
        defender=defender,
        hit_probability=opposed_summary.probability_attacker_win,
        tie_probability=opposed_summary.probability_tie,
        expected_incoming_damage=opposed_summary.expected_positive_margin,
        expected_damage_after_armor=expected_damage_after_armor,
        probability_no_injury=probability_no_injury,
        probability_minor_injury=probability_minor_injury,
        probability_major_injury=probability_major_injury,
        probability_unconscious=probability_unconscious,
    )


@cache
def _sampling_table(rank: SkillRank | int) -> tuple[np.ndarray, np.ndarray]:
    distribution = distribution_for_rank(coerce_skill_rank(rank))
    outcomes = np.array([result for result, _ in distribution.ordered_pmf], dtype=np.int16)
    probabilities = np.array(
        [float(probability) for _, probability in distribution.ordered_pmf],
        dtype=float,
    )
    cumulative = np.cumsum(probabilities)
    cumulative[-1] = 1.0
    return outcomes, cumulative


def _sample_result(rank: SkillRank | int, rng: np.random.Generator) -> int:
    outcomes, cumulative = _sampling_table(rank)
    index = int(np.searchsorted(cumulative, rng.random(), side="right"))
    return int(outcomes[index])


def _record_round_state(
    state: CombatState,
    round_index: int,
    any_minor: np.ndarray,
    any_major: np.ndarray,
    unconscious: np.ndarray,
    average_minor: np.ndarray,
    average_major: np.ndarray,
) -> None:
    any_minor[round_index] += float(state.minor_injuries > 0)
    any_major[round_index] += float(state.major_injuries > 0)
    unconscious[round_index] += float(state.unconscious)
    average_minor[round_index] += state.minor_injuries
    average_major[round_index] += state.major_injuries


def _build_round_summary(
    round_number: int,
    trials: int,
    any_minor: np.ndarray,
    any_major: np.ndarray,
    unconscious: np.ndarray,
    average_minor: np.ndarray,
    average_major: np.ndarray,
) -> CombatantRoundSummary:
    return CombatantRoundSummary(
        probability_any_minor_injury=float(any_minor[round_number - 1] / trials),
        probability_any_major_injury=float(any_major[round_number - 1] / trials),
        probability_unconscious=float(unconscious[round_number - 1] / trials),
        average_minor_injuries=float(average_minor[round_number - 1] / trials),
        average_major_injuries=float(average_major[round_number - 1] / trials),
    )


def _has_conscious_combatants(states: list[CombatState]) -> bool:
    return any(not state.unconscious for state in states)


def _conscious_indices(states: list[CombatState]) -> list[int]:
    return [index for index, state in enumerate(states) if not state.unconscious]


def _choose_random_target_index(
    states: list[CombatState],
    rng: np.random.Generator,
) -> int | None:
    conscious_indices = _conscious_indices(states)
    if not conscious_indices:
        return None
    return int(rng.choice(np.array(conscious_indices, dtype=np.int16)))


def _roll_initiative_order(
    team_one_states: list[CombatState],
    team_two_states: list[CombatState],
    rng: np.random.Generator,
) -> tuple[_InitiativeEntry, ...]:
    entries: list[_InitiativeEntry] = []

    for team_number, states in ((1, team_one_states), (2, team_two_states)):
        for combatant_index, state in enumerate(states):
            initiative_rank = state.combatant.combat.initiative_skill_rank
            entries.append(
                _InitiativeEntry(
                    team_number=team_number,
                    combatant_index=combatant_index,
                    initiative_result=_sample_result(initiative_rank, rng),
                    initiative_rank=initiative_rank,
                    random_tiebreaker=float(rng.random()),
                )
            )

    entries.sort(
        key=lambda entry: (
            -entry.initiative_result,
            -int(entry.initiative_rank),
            entry.random_tiebreaker,
        )
    )
    return tuple(entries)


def _record_team_state(
    states: list[CombatState],
    round_index: int,
    team_defeated: np.ndarray,
    average_unconscious: np.ndarray,
    average_minor: np.ndarray,
    average_major: np.ndarray,
) -> None:
    unconscious_count = sum(int(state.unconscious) for state in states)
    team_defeated[round_index] += float(unconscious_count == len(states))
    average_unconscious[round_index] += unconscious_count
    average_minor[round_index] += sum(state.minor_injuries for state in states)
    average_major[round_index] += sum(state.major_injuries for state in states)


def _build_team_round_summary(
    round_number: int,
    trials: int,
    team_defeated: np.ndarray,
    average_unconscious: np.ndarray,
    average_minor: np.ndarray,
    average_major: np.ndarray,
) -> TeamRoundSummary:
    return TeamRoundSummary(
        probability_team_defeated=float(team_defeated[round_number - 1] / trials),
        average_unconscious_combatants=float(average_unconscious[round_number - 1] / trials),
        average_minor_injuries=float(average_minor[round_number - 1] / trials),
        average_major_injuries=float(average_major[round_number - 1] / trials),
    )


def simulate_duel(
    attacker: Combatant,
    defender: Combatant,
    config: DuelSimulationConfig,
) -> DuelSimulationResult:
    """Run a seeded two-combatant duel simulation."""
    rng = np.random.default_rng(config.seed)
    round_count = config.max_rounds

    attacker_any_minor = np.zeros(round_count, dtype=float)
    attacker_any_major = np.zeros(round_count, dtype=float)
    attacker_unconscious = np.zeros(round_count, dtype=float)
    attacker_average_minor = np.zeros(round_count, dtype=float)
    attacker_average_major = np.zeros(round_count, dtype=float)

    defender_any_minor = np.zeros(round_count, dtype=float)
    defender_any_major = np.zeros(round_count, dtype=float)
    defender_unconscious = np.zeros(round_count, dtype=float)
    defender_average_minor = np.zeros(round_count, dtype=float)
    defender_average_major = np.zeros(round_count, dtype=float)

    attacker_wins = 0
    defender_wins = 0
    resolved_round_total = 0
    resolved_trials = 0

    for _ in range(config.trials):
        attacker_state = fresh_combat_state(attacker)
        defender_state = fresh_combat_state(defender)
        resolution_round: int | None = None

        for round_index in range(round_count):
            if not attacker_state.unconscious and not defender_state.unconscious:
                attacker_result = _sample_result(attacker.combat.attack_skill_rank, rng)
                defender_result = _sample_result(defender.combat.defense_skill_rank, rng)
                defender_state = resolve_martial_attack(
                    attacker_result,
                    defender_result,
                    defender_state,
                ).target_state

            if not attacker_state.unconscious and not defender_state.unconscious:
                defender_attack_result = _sample_result(defender.combat.attack_skill_rank, rng)
                attacker_defense_result = _sample_result(attacker.combat.defense_skill_rank, rng)
                attacker_state = resolve_martial_attack(
                    defender_attack_result,
                    attacker_defense_result,
                    attacker_state,
                ).target_state

            _record_round_state(
                attacker_state,
                round_index,
                attacker_any_minor,
                attacker_any_major,
                attacker_unconscious,
                attacker_average_minor,
                attacker_average_major,
            )
            _record_round_state(
                defender_state,
                round_index,
                defender_any_minor,
                defender_any_major,
                defender_unconscious,
                defender_average_minor,
                defender_average_major,
            )

            if resolution_round is None:
                if defender_state.unconscious:
                    attacker_wins += 1
                    resolution_round = round_index + 1
                elif attacker_state.unconscious:
                    defender_wins += 1
                    resolution_round = round_index + 1

        if resolution_round is not None:
            resolved_trials += 1
            resolved_round_total += resolution_round

    if resolved_trials:
        average_rounds_to_resolution = resolved_round_total / resolved_trials
    else:
        average_rounds_to_resolution = None

    unresolved_trials = config.trials - attacker_wins - defender_wins
    round_summaries = tuple(
        DuelRoundSummary(
            round_number=round_number,
            attacker=_build_round_summary(
                round_number,
                config.trials,
                attacker_any_minor,
                attacker_any_major,
                attacker_unconscious,
                attacker_average_minor,
                attacker_average_major,
            ),
            defender=_build_round_summary(
                round_number,
                config.trials,
                defender_any_minor,
                defender_any_major,
                defender_unconscious,
                defender_average_minor,
                defender_average_major,
            ),
        )
        for round_number in range(1, round_count + 1)
    )

    return DuelSimulationResult(
        attacker=attacker,
        defender=defender,
        config=config,
        opening_attack=analyze_opening_attack(attacker, defender),
        attacker_win_rate=attacker_wins / config.trials,
        defender_win_rate=defender_wins / config.trials,
        unresolved_rate=unresolved_trials / config.trials,
        average_rounds_to_resolution=average_rounds_to_resolution,
        round_summaries=round_summaries,
    )


def simulate_team_battle(
    team_one: CombatTeam,
    team_two: CombatTeam,
    config: DuelSimulationConfig,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> TeamBattleSimulationResult:
    """Run a seeded team-vs-team battle simulation."""
    rng = np.random.default_rng(config.seed)
    round_count = config.max_rounds
    progress_interval = max(1, config.trials // 100)

    team_one_defeated = np.zeros(round_count, dtype=float)
    team_one_average_unconscious = np.zeros(round_count, dtype=float)
    team_one_average_minor = np.zeros(round_count, dtype=float)
    team_one_average_major = np.zeros(round_count, dtype=float)

    team_two_defeated = np.zeros(round_count, dtype=float)
    team_two_average_unconscious = np.zeros(round_count, dtype=float)
    team_two_average_minor = np.zeros(round_count, dtype=float)
    team_two_average_major = np.zeros(round_count, dtype=float)

    team_one_wins = 0
    team_two_wins = 0
    resolved_round_total = 0
    resolved_trials = 0

    reference_strike = analyze_opening_attack(
        team_one.combatants[0],
        team_two.combatants[0],
    )

    if progress_callback is not None:
        progress_callback(0, config.trials)

    for trial_index in range(config.trials):
        team_one_states = [fresh_combat_state(combatant) for combatant in team_one.combatants]
        team_two_states = [fresh_combat_state(combatant) for combatant in team_two.combatants]
        initiative_order = _roll_initiative_order(team_one_states, team_two_states, rng)
        resolution_round: int | None = None

        for round_index in range(round_count):
            both_teams_active = (
                _has_conscious_combatants(team_one_states)
                and _has_conscious_combatants(team_two_states)
            )
            if both_teams_active:
                for actor in initiative_order:
                    acting_team_states = (
                        team_one_states if actor.team_number == 1 else team_two_states
                    )
                    opposing_team_states = (
                        team_two_states if actor.team_number == 1 else team_one_states
                    )
                    acting_state = acting_team_states[actor.combatant_index]

                    if acting_state.unconscious:
                        continue

                    target_index = _choose_random_target_index(opposing_team_states, rng)
                    if target_index is None:
                        break

                    attacker_result = _sample_result(
                        acting_state.combatant.combat.attack_skill_rank,
                        rng,
                    )
                    defender_result = _sample_result(
                        opposing_team_states[target_index].combatant.combat.defense_skill_rank,
                        rng,
                    )
                    opposing_team_states[target_index] = resolve_martial_attack(
                        attacker_result,
                        defender_result,
                        opposing_team_states[target_index],
                    ).target_state

                    if not _has_conscious_combatants(opposing_team_states):
                        break

            _record_team_state(
                team_one_states,
                round_index,
                team_one_defeated,
                team_one_average_unconscious,
                team_one_average_minor,
                team_one_average_major,
            )
            _record_team_state(
                team_two_states,
                round_index,
                team_two_defeated,
                team_two_average_unconscious,
                team_two_average_minor,
                team_two_average_major,
            )

            if resolution_round is None:
                if not _has_conscious_combatants(team_two_states):
                    team_one_wins += 1
                    resolution_round = round_index + 1
                elif not _has_conscious_combatants(team_one_states):
                    team_two_wins += 1
                    resolution_round = round_index + 1

        if resolution_round is not None:
            resolved_trials += 1
            resolved_round_total += resolution_round

        completed_trials = trial_index + 1
        if (
            progress_callback is not None
            and (
                completed_trials == config.trials
                or completed_trials % progress_interval == 0
            )
        ):
            progress_callback(completed_trials, config.trials)

    if resolved_trials:
        average_rounds_to_resolution = resolved_round_total / resolved_trials
    else:
        average_rounds_to_resolution = None

    unresolved_trials = config.trials - team_one_wins - team_two_wins
    round_summaries = tuple(
        TeamBattleRoundSummary(
            round_number=round_number,
            team_one=_build_team_round_summary(
                round_number,
                config.trials,
                team_one_defeated,
                team_one_average_unconscious,
                team_one_average_minor,
                team_one_average_major,
            ),
            team_two=_build_team_round_summary(
                round_number,
                config.trials,
                team_two_defeated,
                team_two_average_unconscious,
                team_two_average_minor,
                team_two_average_major,
            ),
        )
        for round_number in range(1, round_count + 1)
    )

    return TeamBattleSimulationResult(
        team_one=team_one,
        team_two=team_two,
        config=config,
        reference_strike=reference_strike,
        team_one_win_rate=team_one_wins / config.trials,
        team_two_win_rate=team_two_wins / config.trials,
        unresolved_rate=unresolved_trials / config.trials,
        average_rounds_to_resolution=average_rounds_to_resolution,
        round_summaries=round_summaries,
    )
