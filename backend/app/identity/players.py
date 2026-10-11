"""Canonical player records and the id crosswalk."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    """Accent-fold, lowercase, strip punctuation and generational suffixes: 'Luka Dončić' -> 'luka doncic'."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    parts = [p for p in s.split() if p not in SUFFIXES]
    return " ".join(parts)


@dataclass(frozen=True)
class Player:
    player_id: str  # canonical: "nba:<id>" when an NBA id exists, "espn:<id>" or "demo:<n>" otherwise
    name: str
    team: str | None = None
    nba_id: int | None = None
    espn_id: int | None = None
    primary_position: str | None = None
    eligible_positions: frozenset[str] = field(default_factory=frozenset)
    eligibility_source: str = "unknown"  # espn | import | manual | demo | unknown
    eligibility_verified: bool = False
    injury_status: str | None = None
    age: float | None = None
    years_experience: int | None = None
    is_rookie: bool = False
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["eligible_positions"] = sorted(self.eligible_positions)
        d["aliases"] = list(self.aliases)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Player:
        d = dict(d)
        d["eligible_positions"] = frozenset(d.get("eligible_positions") or ())
        d["aliases"] = tuple(d.get("aliases") or ())
        return Player(**d)

    @property
    def search_keys(self) -> tuple[str, ...]:
        return (normalize_name(self.name), *(normalize_name(a) for a in self.aliases))
