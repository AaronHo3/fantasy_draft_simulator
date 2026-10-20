"""League configuration: categories, scoring format, slots, managers, draft rules.

Three position concepts are kept separate (see CLAUDE.md):
1. a player's ESPN primary position (``defaultPositionId``) — used for primary-position caps;
2. a player's ESPN eligible primitive positions (derived from ``eligibleSlots``);
3. the league's lineup slots and which primitive positions each slot accepts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PRIMITIVE_POSITIONS: tuple[str, ...] = ("PG", "SG", "SF", "PF", "C")

# Slot -> primitive positions that may fill it. Matches ESPN's slot semantics.
SLOT_COMPATIBILITY: dict[str, frozenset[str]] = {
    "PG": frozenset({"PG"}),
    "SG": frozenset({"SG"}),
    "SF": frozenset({"SF"}),
    "PF": frozenset({"PF"}),
    "C": frozenset({"C"}),
    "G": frozenset({"PG", "SG"}),
    "F": frozenset({"SF", "PF"}),
    "SG/SF": frozenset({"SG", "SF"}),
    "G/F": frozenset({"PG", "SG", "SF", "PF"}),
    "PF/C": frozenset({"PF", "C"}),
    "F/C": frozenset({"SF", "PF", "C"}),
    "UTIL": frozenset(PRIMITIVE_POSITIONS),
    "BENCH": frozenset(PRIMITIVE_POSITIONS),
    "IR": frozenset(PRIMITIVE_POSITIONS),
}

# ESPN eligibleSlots ids (0-indexed) -> slot names. From espn_api basketball/constant.py.
ESPN_SLOT_ID_TO_NAME: dict[int, str] = {
    0: "PG",
    1: "SG",
    2: "SF",
    3: "PF",
    4: "C",
    5: "G",
    6: "F",
    7: "SG/SF",
    8: "G/F",
    9: "PF/C",
    10: "F/C",
    11: "UTIL",
    12: "BENCH",
    13: "IR",
}
# ESPN defaultPositionId (1-indexed!) -> primary position.
ESPN_DEFAULT_POSITION_ID_TO_NAME: dict[int, str] = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}


def espn_season_id(nba_season: str) -> int:
    """'2026-27' -> 2027. ESPN seasonId is the season's end year (verified via schedule dates)."""
    start, end2 = nba_season.split("-")
    start_i = int(start)
    end_i = int(str(start_i)[:2] + end2)
    if end_i != start_i + 1:
        raise ValueError(f"malformed NBA season string: {nba_season!r}")
    return end_i


def nba_season_from_espn(season_id: int) -> str:
    return f"{season_id - 1}-{str(season_id)[-2:]}"


def eligible_positions_from_espn_slots(slot_ids: list[int]) -> frozenset[str]:
    """Primitive positions implied by ESPN eligibleSlots (only the five primitive slot ids)."""
    return frozenset(ESPN_SLOT_ID_TO_NAME[s] for s in slot_ids if s in range(0, 5))


class CategoryKind(StrEnum):
    counting = "counting"
    ratio = "ratio"


class CategoryDef(BaseModel):
    key: str
    label: str
    higher_is_better: bool = True
    kind: CategoryKind = CategoryKind.counting
    numerator: str | None = None  # primitive key for ratio categories
    denominator: str | None = None

    @model_validator(mode="after")
    def _check_ratio(self) -> CategoryDef:
        if self.kind == CategoryKind.ratio and not (self.numerator and self.denominator):
            raise ValueError(f"ratio category {self.key} needs numerator and denominator")
        return self


DEFAULT_NINE_CATEGORIES: list[CategoryDef] = [
    CategoryDef(key="PTS", label="Points"),
    CategoryDef(key="REB", label="Rebounds"),
    CategoryDef(key="AST", label="Assists"),
    CategoryDef(key="STL", label="Steals"),
    CategoryDef(key="BLK", label="Blocks"),
    CategoryDef(key="FG3M", label="Threes made"),
    CategoryDef(key="FG_PCT", label="FG%", kind=CategoryKind.ratio, numerator="FGM", denominator="FGA"),
    CategoryDef(key="FT_PCT", label="FT%", kind=CategoryKind.ratio, numerator="FTM", denominator="FTA"),
    CategoryDef(key="TOV", label="Turnovers", higher_is_better=False),
]


class ScoringFormat(StrEnum):
    h2h_each_category = "h2h_each_category"
    h2h_most_categories = "h2h_most_categories"
    roto = "roto"


class TieRule(BaseModel):
    """How a tied category is scored.

    each_category_tie_value: credit for a tied category in each-category scoring (0 or 0.5).
    most_categories_tie: in most-categories scoring, a tied category counts for neither side; the
    matchup is a tie when category wins are equal unless ``matchup_tie_breaker`` is set.
    zero_attempts: how a team with zero attempts is treated in a ratio category.
    """

    each_category_tie_value: float = Field(default=0.5, ge=0.0, le=1.0)
    matchup_tie_breaker: Literal["none", "points", "total_categories"] = "none"
    zero_attempts: Literal["loss", "tie", "unknown"] = "unknown"


class LineupMode(StrEnum):
    weekly = "weekly"
    daily = "daily"


class Manager(BaseModel):
    id: str
    name: str
    is_user: bool = False


class Keeper(BaseModel):
    manager_id: str
    player_id: str
    round: int = Field(ge=1)


class TradedPick(BaseModel):
    round: int = Field(ge=1)
    from_manager_id: str
    to_manager_id: str


class LeagueConfig(BaseModel):
    name: str = "My ESPN 9-cat league"
    platform: Literal["espn", "custom"] = "espn"
    season: str = "2026-27"
    scoring_format: ScoringFormat = ScoringFormat.h2h_each_category
    format_confirmed: bool = False
    categories: list[CategoryDef] = Field(default_factory=lambda: list(DEFAULT_NINE_CATEGORIES))
    tie_rule: TieRule = Field(default_factory=TieRule)
    managers: list[Manager]
    user_manager_id: str
    starting_slots: list[str] = Field(
        default_factory=lambda: ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL", "UTIL", "UTIL"]
    )
    bench_slots: int = Field(default=3, ge=0)
    ir_slots: int = Field(default=1, ge=0)
    draft_type: Literal["snake", "linear", "custom"] = "snake"
    draft_order: list[str] = Field(default_factory=list, description="manager ids in round-1 order")
    third_round_reversal: bool = False
    keepers: list[Keeper] = Field(default_factory=list)
    traded_picks: list[TradedPick] = Field(default_factory=list)
    position_caps: dict[str, int] = Field(default_factory=lambda: {"C": 4}, description="primary position -> max")
    position_minimums: dict[str, int] = Field(default_factory=dict)
    lineup_mode: LineupMode = LineupMode.weekly
    max_games_per_week: int | None = None
    regular_season_weeks: int = 19
    playoff_weeks: int = 3
    strict_eligibility: bool = False  # exclude players with unverified eligibility when True
    # Optional read-only link to a public ESPN league (set by the link flow, never by hand).
    espn_league_id: int | None = Field(default=None, gt=0)
    espn_team_ids: dict[str, int] = Field(default_factory=dict, description="manager id -> ESPN team id")
    espn_linked_at: str | None = None

    @property
    def roster_size(self) -> int:
        return len(self.starting_slots) + self.bench_slots

    @property
    def n_rounds(self) -> int:
        return self.roster_size

    @property
    def n_managers(self) -> int:
        return len(self.managers)

    def manager(self, manager_id: str) -> Manager:
        for m in self.managers:
            if m.id == manager_id:
                return m
        raise KeyError(manager_id)

    def category(self, key: str) -> CategoryDef:
        for c in self.categories:
            if c.key == key:
                return c
        raise KeyError(key)

    @model_validator(mode="after")
    def _validate(self) -> LeagueConfig:
        ids = [m.id for m in self.managers]
        if len(ids) != len(set(ids)):
            raise ValueError("manager ids must be unique")
        if len(ids) < 2:
            raise ValueError("a league needs at least two managers")
        if self.user_manager_id not in ids:
            raise ValueError("user_manager_id must be one of the managers")
        if not self.draft_order:
            object.__setattr__(self, "draft_order", list(ids))
        if sorted(self.draft_order) != sorted(ids):
            raise ValueError("draft_order must be a permutation of manager ids")
        if any(m not in ids for m in self.espn_team_ids):
            raise ValueError("espn_team_ids keys must be manager ids")
        if len(set(self.espn_team_ids.values())) != len(self.espn_team_ids):
            raise ValueError("espn_team_ids must map each manager to a distinct ESPN team")
        for s in self.starting_slots:
            if s not in SLOT_COMPATIBILITY or s in ("BENCH", "IR"):
                raise ValueError(f"unknown starting slot {s!r}")
        keys = [c.key for c in self.categories]
        if len(keys) != len(set(keys)):
            raise ValueError("category keys must be unique")
        for k in self.keepers:
            if k.manager_id not in ids:
                raise ValueError(f"keeper manager {k.manager_id} unknown")
            if k.round > self.n_rounds:
                raise ValueError("keeper round beyond roster size")
        for t in self.traded_picks:
            if t.from_manager_id not in ids or t.to_manager_id not in ids:
                raise ValueError("traded pick references unknown manager")
        for p in list(self.position_caps) + list(self.position_minimums):
            if p not in PRIMITIVE_POSITIONS:
                raise ValueError(f"position cap/min for unknown position {p!r}")
        return self


def demo_league_config(user_pick: int = 6, n_managers: int = 12) -> LeagueConfig:
    """Defaults matching the user's league (2026-10-10): H2H each category with ties allowed (half credit),
    12 managers, snake, 10 starters + 3 bench + 1 IR, max 4 centers, weekly lineups. The user's draft
    position is unknown until draft day, so ``user_pick`` is a placeholder changed in the UI.
    """
    managers = [
        Manager(id=f"m{i + 1:02d}", name=f"Team {i + 1}", is_user=(i + 1 == user_pick)) for i in range(n_managers)
    ]
    return LeagueConfig(
        name="Demo 12-team 9-cat (synthetic)",
        managers=managers,
        user_manager_id=f"m{user_pick:02d}",
        draft_order=[m.id for m in managers],
    )
