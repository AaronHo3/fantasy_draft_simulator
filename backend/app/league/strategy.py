"""User strategy: punts, category weights, risk preference, simulation budget."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PuntKind(StrEnum):
    fixed = "fixed"  # weight 0 in the screening utility
    soft = "soft"  # reduced weight


class RiskPreference(StrEnum):
    conservative = "conservative"
    neutral = "neutral"
    aggressive = "aggressive"


class Strategy(BaseModel):
    mode: str = Field(default="balanced", description="balanced | custom")
    punts: dict[str, PuntKind] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict, description="category -> emphasis weight")
    soft_punt_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    risk: RiskPreference = RiskPreference.neutral
    suggest_punts: bool = False  # suggestions are shown but never applied automatically
    sim_budget_ms: int = Field(default=4000, ge=100, le=30000)  # picks take ~10 s+; 4 s leaves slack
    sim_scenarios: int = Field(default=400, ge=20, le=20000)
    projection_blend_espn_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    roster_aware: bool = False  # diminishing-returns weighting; off by default (hurt in paired drafts, DEC-22)
    roster_scale: float = Field(default=3.6, gt=0.0)  # sd of a full roster's category z-total relative to the league

    def category_weight(self, key: str) -> float:
        kind = self.punts.get(key)
        if kind == PuntKind.fixed:
            return 0.0
        base = self.weights.get(key, 1.0)
        if kind == PuntKind.soft:
            return base * self.soft_punt_weight
        return base

    def weight_vector(self, keys: list[str]) -> list[float]:
        return [self.category_weight(k) for k in keys]

    def fixed_punts(self) -> list[str]:
        return [k for k, v in self.punts.items() if v == PuntKind.fixed]
