"""Typed domain models shared across the analytical engine and the GUI."""

from __future__ import annotations

from enum import IntEnum
from fractions import Fraction
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

SKILL_RANK_TO_DICE: dict[int, tuple[int, ...]] = {
    1: (4,),
    2: (4, 6),
    3: (4, 6, 8),
    4: (4, 6, 8, 10),
    5: (4, 6, 8, 10, 12),
    6: (4, 6, 8, 10, 12, 20),
}

SKILL_RANK_TO_LABEL: dict[int, str] = {
    1: "d4",
    2: "d4-d6",
    3: "d4-d8",
    4: "d4-d10",
    5: "d4-d12",
    6: "d4-d20",
}


class SkillRank(IntEnum):
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6

    @property
    def dice(self) -> tuple[int, ...]:
        return SKILL_RANK_TO_DICE[int(self)]

    @property
    def label(self) -> str:
        return SKILL_RANK_TO_LABEL[int(self)]

    @property
    def full_label(self) -> str:
        return " + ".join(f"1d{die}" for die in self.dice)


ALL_SKILL_RANKS: tuple[SkillRank, ...] = tuple(SkillRank(value) for value in range(1, 7))


def coerce_skill_rank(rank: SkillRank | int) -> SkillRank:
    if isinstance(rank, SkillRank):
        return rank
    return SkillRank(rank)


class DicePool(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: SkillRank
    dice: tuple[int, ...]
    label: str
    full_label: str

    @classmethod
    def for_rank(cls, rank: SkillRank | int) -> DicePool:
        skill_rank = coerce_skill_rank(rank)
        return cls(
            rank=skill_rank,
            dice=skill_rank.dice,
            label=skill_rank.label,
            full_label=skill_rank.full_label,
        )

    @model_validator(mode="after")
    def validate_consistency(self) -> DicePool:
        expected = DicePool.model_construct(
            rank=self.rank,
            dice=self.rank.dice,
            label=self.rank.label,
            full_label=self.rank.full_label,
        )
        if (
            self.dice != expected.dice
            or self.label != expected.label
            or self.full_label != expected.full_label
        ):
            msg = f"dice pool metadata does not match rank {self.rank}"
            raise ValueError(msg)
        return self


def all_dice_pools() -> tuple[DicePool, ...]:
    return tuple(DicePool.for_rank(rank) for rank in ALL_SKILL_RANKS)


class Armor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rating: int = Field(default=0, ge=0)


class InjuryTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minor_capacity: int = Field(default=2, ge=0)
    major_capacity: int = Field(default=2, ge=0)


class CombatProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attack_skill_rank: SkillRank
    defense_skill_rank: SkillRank
    initiative_skill_rank: SkillRank

    @model_validator(mode="before")
    @classmethod
    def normalize_skill_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "skill_rank" in normalized:
            skill_rank = normalized.pop("skill_rank")
            normalized.setdefault("attack_skill_rank", skill_rank)
            normalized.setdefault("defense_skill_rank", skill_rank)
            normalized.setdefault("initiative_skill_rank", skill_rank)

        if "attack_skill_rank" in normalized and "defense_skill_rank" not in normalized:
            normalized["defense_skill_rank"] = normalized["attack_skill_rank"]
        if "defense_skill_rank" in normalized and "attack_skill_rank" not in normalized:
            normalized["attack_skill_rank"] = normalized["defense_skill_rank"]
        if "initiative_skill_rank" not in normalized:
            normalized["initiative_skill_rank"] = normalized.get(
                "attack_skill_rank",
                normalized.get("defense_skill_rank"),
            )
        return normalized

    @property
    def skill_rank(self) -> SkillRank:
        return self.attack_skill_rank


class Combatant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    combat: CombatProfile = Field(validation_alias=AliasChoices("combat", "attack"))
    armor: Armor = Field(default_factory=Armor)
    injury_track: InjuryTrack = Field(default_factory=InjuryTrack)

    @property
    def attack(self) -> CombatProfile:
        return self.combat


AttackProfile = CombatProfile


class RollDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pool: DicePool
    pmf: dict[int, Fraction]

    @model_validator(mode="after")
    def validate_probability_mass(self) -> RollDistribution:
        total = sum(self.pmf.values(), start=Fraction())
        if total != Fraction(1, 1):
            msg = f"probability mass must sum to 1, got {total}"
            raise ValueError(msg)
        return self

    @property
    def ordered_pmf(self) -> tuple[tuple[int, Fraction], ...]:
        return tuple(sorted(self.pmf.items()))

    def probability_of(self, result: int) -> Fraction:
        return self.pmf.get(result, Fraction())


class StaticCheckSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pool: DicePool
    dc: int = Field(ge=0)
    probability_gt: Fraction
    probability_eq: Fraction
    probability_gte: Fraction


class OpposedRollSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attacker_pool: DicePool
    defender_pool: DicePool
    probability_attacker_win: Fraction
    probability_tie: Fraction
    expected_positive_margin: Fraction
