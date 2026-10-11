"""Synthetic, clearly labeled demo dataset: ~600 fake players on 30 fake teams.

Nothing here is a real player. Names are generated from syllables; teams are 'DEMO-xx'. The
snapshot is flagged ``is_demo=True`` and ``source='demo'`` so the UI can label it everywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from app.engine.categories import PRIM_IDX, PRIMITIVES
from app.identity.players import Player
from app.projections.snapshot import Snapshot, content_hash

DEMO_TEAMS = [f"DM{i:02d}" for i in range(1, 31)]
FIRST = [
    "Tav",
    "Bren",
    "Kor",
    "Dal",
    "Mar",
    "Jal",
    "Rhy",
    "Zen",
    "Cal",
    "Ori",
    "Lan",
    "Vic",
    "Nol",
    "Quin",
    "Ash",
    "Dev",
    "Kai",
    "Rom",
    "Sol",
    "Tre",
    "Ev",
    "Jor",
    "Mal",
    "Ren",
]
FIRST2 = ["on", "an", "el", "en", "ik", "us", "o", "ian", "is", "ar", "ey", "in"]
LAST = [
    "Breck",
    "Hollan",
    "Vance",
    "Marl",
    "Okon",
    "Stav",
    "Rook",
    "Ferr",
    "Dunmo",
    "Keel",
    "Tallis",
    "Brant",
    "Varg",
    "Oswin",
    "Pell",
    "Garr",
    "Lind",
    "Mosk",
    "Harl",
    "Quill",
    "Rand",
    "Whit",
]
LAST2 = ["er", "ow", "ston", "ard", "ey", "is", "man", "ell", "ley", "ridge", "wood", "son"]

# archetype: (primary pos weights) and per-36 means for PTS REB AST STL BLK FG3M FG3A FGA FG% FTA FT% TOV
ARCHETYPES = {
    "creator_guard": dict(
        pos=("PG", "SG"),
        pts=24,
        reb=4.5,
        ast=7.5,
        stl=1.3,
        blk=0.3,
        fg3m=2.6,
        fg3a=7.5,
        fga=18,
        fgp=0.46,
        fta=6.0,
        ftp=0.84,
        tov=3.4,
    ),
    "assist_guard": dict(
        pos=("PG",),
        pts=15,
        reb=4.0,
        ast=9.0,
        stl=1.4,
        blk=0.3,
        fg3m=1.6,
        fg3a=4.8,
        fga=12,
        fgp=0.46,
        fta=3.0,
        ftp=0.82,
        tov=3.0,
    ),
    "shooter_wing": dict(
        pos=("SG", "SF"),
        pts=17,
        reb=4.0,
        ast=2.2,
        stl=1.0,
        blk=0.4,
        fg3m=3.2,
        fg3a=8.5,
        fga=13,
        fgp=0.44,
        fta=2.5,
        ftp=0.86,
        tov=1.3,
    ),
    "three_and_d": dict(
        pos=("SF", "PF"),
        pts=13,
        reb=5.5,
        ast=2.0,
        stl=1.4,
        blk=0.8,
        fg3m=2.2,
        fg3a=6.0,
        fga=10,
        fgp=0.46,
        fta=2.0,
        ftp=0.78,
        tov=1.2,
    ),
    "point_forward": dict(
        pos=("SF", "PF"),
        pts=21,
        reb=7.5,
        ast=6.0,
        stl=1.1,
        blk=0.7,
        fg3m=1.8,
        fg3a=5.0,
        fga=16,
        fgp=0.49,
        fta=5.5,
        ftp=0.80,
        tov=3.0,
    ),
    "stretch_big": dict(
        pos=("PF", "C"),
        pts=17,
        reb=8.5,
        ast=2.5,
        stl=0.7,
        blk=1.3,
        fg3m=1.9,
        fg3a=5.0,
        fga=12,
        fgp=0.50,
        fta=3.5,
        ftp=0.80,
        tov=1.6,
    ),
    "rim_protector": dict(
        pos=("C",),
        pts=12,
        reb=11.0,
        ast=1.5,
        stl=0.7,
        blk=2.3,
        fg3m=0.1,
        fg3a=0.3,
        fga=8,
        fgp=0.63,
        fta=3.5,
        ftp=0.62,
        tov=1.5,
    ),
    "interior_scorer": dict(
        pos=("PF", "C"),
        pts=23,
        reb=10.5,
        ast=3.5,
        stl=0.9,
        blk=1.3,
        fg3m=0.6,
        fg3a=1.8,
        fga=16,
        fgp=0.56,
        fta=7.5,
        ftp=0.72,
        tov=2.8,
    ),
    "glue_forward": dict(
        pos=("SF", "PF"),
        pts=10,
        reb=6.0,
        ast=2.5,
        stl=1.0,
        blk=0.7,
        fg3m=1.2,
        fg3a=3.5,
        fga=8,
        fgp=0.48,
        fta=2.0,
        ftp=0.75,
        tov=1.2,
    ),
}
ARCH_NAMES = list(ARCHETYPES)
NEIGHBOR = {"PG": "SG", "SG": "SF", "SF": "PF", "PF": "C", "C": "PF"}


def _name(rng: np.random.Generator) -> str:
    return (rng.choice(FIRST) + rng.choice(FIRST2) + " " + rng.choice(LAST) + rng.choice(LAST2)).strip()


def generate_demo_snapshot(n_players: int = 600, seed: int = 7) -> Snapshot:
    rng = np.random.default_rng(seed)
    n = n_players
    # minutes tiers: ~150 starters 30-36, ~150 rotation 20-30, rest 8-20
    n0 = max(1, round(0.25 * n))
    n1 = max(1, round(0.25 * n))
    tier = np.concatenate([np.zeros(n0), np.ones(n1), np.full(n - n0 - n1, 2)]).astype(int)
    minutes = np.where(
        tier == 0, rng.uniform(29, 36.5, n), np.where(tier == 1, rng.uniform(19, 29, n), rng.uniform(6, 19, n))
    )
    quality = np.where(
        tier == 0, rng.normal(1.08, 0.12, n), np.where(tier == 1, rng.normal(0.95, 0.10, n), rng.normal(0.85, 0.10, n))
    )
    games = np.clip(np.round(rng.beta(6, 1.6, n) * 82), 20, 82)
    games[tier == 2] = np.clip(games[tier == 2] - rng.integers(0, 20, (tier == 2).sum()), 10, 82)

    pg = np.zeros((n, len(PRIMITIVES)))
    sd = np.zeros((n, len(PRIMITIVES)))
    players: list[Player] = []
    used_names: set[str] = set()
    for i in range(n):
        a = ARCHETYPES[ARCH_NAMES[rng.integers(len(ARCH_NAMES))]]
        prim = str(rng.choice(a["pos"]))
        elig = {prim}
        if rng.random() < 0.38:
            elig.add(NEIGHBOR[prim])
        m = minutes[i] / 36.0
        q = quality[i]
        noise = lambda s: float(np.exp(rng.normal(0, s)))  # noqa: E731
        fga = a["fga"] * m * q * noise(0.12)
        fg3a = min(a["fg3a"] * m * q * noise(0.25), fga)
        fgp = float(np.clip(a["fgp"] + rng.normal(0, 0.025), 0.36, 0.72))
        fgm = fga * fgp
        fg3p = float(np.clip(0.36 + rng.normal(0, 0.03), 0.25, 0.45))
        fg3m = min(fg3a * fg3p, fgm)
        fta = a["fta"] * m * q * noise(0.2)
        ftp = float(np.clip(a["ftp"] + rng.normal(0, 0.04), 0.45, 0.93))
        ftm = fta * ftp
        pts = 2 * fgm + fg3m + ftm
        row = {
            "MIN": minutes[i],
            "GP": games[i],
            "PTS": pts,
            "REB": a["reb"] * m * noise(0.15),
            "AST": a["ast"] * m * noise(0.2),
            "STL": a["stl"] * m * noise(0.25),
            "BLK": a["blk"] * m * noise(0.3),
            "FG3M": fg3m,
            "FG3A": fg3a,
            "FGM": fgm,
            "FGA": fga,
            "FTM": ftm,
            "FTA": fta,
            "TOV": a["tov"] * m * q * noise(0.15),
        }
        for k, v in row.items():
            pg[i, PRIM_IDX[k]] = v
            sd[i, PRIM_IDX[k]] = (0.12 if tier[i] == 0 else 0.2) * v if k != "GP" else 8.0
        name = _name(rng)
        while name in used_names:
            name = _name(rng)
        used_names.add(name)
        age = float(np.clip(rng.normal(26.5, 4.0), 19, 38))
        players.append(
            Player(
                player_id=f"demo:{i + 1:04d}",
                name=name,
                team=DEMO_TEAMS[i % 30],
                primary_position=prim,
                eligible_positions=frozenset(elig),
                eligibility_source="demo",
                eligibility_verified=True,
                injury_status=("OUT" if rng.random() < 0.02 else "DAY_TO_DAY" if rng.random() < 0.06 else "ACTIVE"),
                age=round(age, 1),
                years_experience=int(max(0, age - 20)),
                is_rookie=age < 20.5,
            )
        )
    # crude demo ADP: rank by a simple value proxy with noise; only top 200 have an ADP
    proxy = (
        pg[:, PRIM_IDX["PTS"]]
        + 1.2 * pg[:, PRIM_IDX["REB"]]
        + 1.5 * pg[:, PRIM_IDX["AST"]]
        + 3 * pg[:, PRIM_IDX["STL"]]
        + 3 * pg[:, PRIM_IDX["BLK"]]
        + pg[:, PRIM_IDX["FG3M"]]
        - pg[:, PRIM_IDX["TOV"]]
    ) * (0.6 + 0.4 * games / 82)
    order = np.argsort(-(proxy + rng.normal(0, 2.5, n)))
    adp = np.full(n, np.nan)
    rank = np.full(n, np.nan)
    for r, idx in enumerate(order, start=1):
        rank[idx] = r
        if r <= 200:
            adp[idx] = max(1.0, r + rng.normal(0, 3 + r / 15))
    created = datetime.now(UTC).isoformat(timespec="seconds")
    sid = "demo-" + content_hash(pg, adp)
    return Snapshot(
        snapshot_id=sid,
        label="Synthetic demo data (not real players)",
        source="demo",
        season="demo",
        created_at=created,
        players=tuple(players),
        per_game=pg,
        per_game_sd=sd,
        adp=adp,
        rank=rank,
        projection_source=tuple(["demo"] * n),
        adp_platform="demo",
        adp_asof=created,
        rank_source="demo",
        is_demo=True,
        provenance={"generator": "app.demo.generate", "seed": seed, "note": "synthetic"},
        health={
            "players": n,
            "with_adp": int(np.isfinite(adp).sum()),
            "unresolved_identities": 0,
            "missing_eligibility": 0,
            "sources": {"demo": {"status": "ok"}},
        },
    )
