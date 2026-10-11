"""CSV import contracts: projections, eligibility, ADP/ranks, draft picks. Preview -> validate -> apply.

Every importer returns an ``ImportPreview`` with per-row errors/warnings and resolved player ids; nothing
is written until ``apply_*`` is called with the preview. Units are fixed by the templates in
data/templates/ (per-game rates, rates as makes/attempts, dates ISO).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.engine.categories import PRIM_IDX, PRIMITIVES
from app.identity.players import Player, normalize_name
from app.league.config import PRIMITIVE_POSITIONS
from app.projections.snapshot import Snapshot, content_hash, validate_snapshot

PROJECTION_COLUMNS = {
    "games": "GP",
    "minutes_per_game": "MIN",
    "pts_per_game": "PTS",
    "reb_per_game": "REB",
    "ast_per_game": "AST",
    "stl_per_game": "STL",
    "blk_per_game": "BLK",
    "fg3m_per_game": "FG3M",
    "fg3a_per_game": "FG3A",
    "fgm_per_game": "FGM",
    "fga_per_game": "FGA",
    "ftm_per_game": "FTM",
    "fta_per_game": "FTA",
    "tov_per_game": "TOV",
}
REQUIRED_PROJECTION = [
    "name",
    "games",
    "minutes_per_game",
    "pts_per_game",
    "reb_per_game",
    "ast_per_game",
    "stl_per_game",
    "blk_per_game",
    "fg3m_per_game",
    "fgm_per_game",
    "fga_per_game",
    "ftm_per_game",
    "fta_per_game",
    "tov_per_game",
]
REQUIRED_ELIGIBILITY = ["name", "eligible_positions"]
REQUIRED_ADP = ["name", "platform"]
REQUIRED_PICKS = ["manager_id", "name"]


@dataclass(frozen=True)
class RowResult:
    row: int  # 1-based data row number
    player_id: str | None
    matched_name: str | None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ImportPreview:
    kind: str
    columns: tuple[str, ...]
    rows: tuple[RowResult, ...]
    missing_columns: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def n_ok(self) -> int:
        return sum(1 for r in self.rows if r.ok)

    @property
    def n_error(self) -> int:
        return sum(1 for r in self.rows if not r.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "columns": list(self.columns),
            "missing_columns": list(self.missing_columns),
            "n_rows": len(self.rows),
            "n_ok": self.n_ok,
            "n_error": self.n_error,
            "notes": list(self.notes),
            "rows": [
                {
                    "row": r.row,
                    "player_id": r.player_id,
                    "matched_name": r.matched_name,
                    "errors": list(r.errors),
                    "warnings": list(r.warnings),
                    "data": r.data,
                }
                for r in self.rows
            ],
        }


def parse_csv(text: str) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    cols = tuple(c.strip() for c in (reader.fieldnames or []))
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    return cols, rows


def resolve_player(
    snapshot: Snapshot, player_id: str, name: str, espn_id: str = "", team: str = ""
) -> tuple[str | None, str | None, str | None]:
    """Resolve by id first, then exact normalized name (+team when ambiguous). Returns (id, name, error)."""
    if player_id:
        if player_id in snapshot.index:
            return player_id, snapshot.players[snapshot.index[player_id]].name, None
        return None, None, f"unknown player_id {player_id!r}"
    if espn_id:
        try:
            eid = int(espn_id)
        except ValueError:
            return None, None, f"espn_id {espn_id!r} is not an integer"
        hits = [p for p in snapshot.players if p.espn_id == eid]
        if len(hits) == 1:
            return hits[0].player_id, hits[0].name, None
    if not name:
        return None, None, "name or player_id required"
    key = normalize_name(name)
    hits = [p for p in snapshot.players if key in p.search_keys]
    if len(hits) > 1 and team:
        hits = [p for p in hits if (p.team or "").upper() == team.upper()]
    if len(hits) == 1:
        return hits[0].player_id, hits[0].name, None
    if not hits:
        return None, None, f"no player named {name!r} in snapshot (use player_id or check spelling)"
    return (
        None,
        None,
        f"ambiguous name {name!r}: {', '.join(f'{p.name} ({p.team}, {p.player_id})' for p in hits)}; add team or player_id",
    )


def _num(row: dict[str, str], col: str, errors: list[str], required: bool = True, lo: float = 0.0) -> float | None:
    v = row.get(col, "")
    if v == "":
        if required:
            errors.append(f"{col} missing")
        return None
    try:
        x = float(v)
    except ValueError:
        errors.append(f"{col}={v!r} is not a number")
        return None
    if x < lo:
        errors.append(f"{col}={x} below {lo}")
    return x


# --- projections -------------------------------------------------------------------------------


def preview_projections(text: str, snapshot: Snapshot) -> ImportPreview:
    cols, rows = parse_csv(text)
    missing = tuple(c for c in REQUIRED_PROJECTION if c not in cols)
    results = []
    notes = ["Units: per-game rates; FG%/FT% are derived from makes/attempts (rows without attempts are rejected)."]
    for i, r in enumerate(rows, start=1):
        errors: list[str] = []
        warns: list[str] = []
        pid, mname, err = resolve_player(snapshot, r.get("player_id", ""), r.get("name", ""), team=r.get("team", ""))
        if err:
            errors.append(err)
        vals: dict[str, float] = {}
        for col, prim in PROJECTION_COLUMNS.items():
            x = _num(r, col, errors, required=(col in REQUIRED_PROJECTION))
            if x is not None:
                vals[prim] = x
        if "FG3A" not in vals and "FG3M" in vals:
            vals["FG3A"] = vals["FG3M"] / 0.36
            warns.append("fg3a_per_game missing: approximated from 3PM at 36%")
        if not errors:
            if vals["GP"] > 82:
                errors.append("games > 82")
            if vals["FGA"] <= 0 or vals["FTA"] < 0:
                errors.append("fga_per_game must be > 0 for a percentage-impact projection")
            if vals["FGM"] > vals["FGA"] + 1e-9:
                errors.append("fgm > fga")
            if vals["FTM"] > vals["FTA"] + 1e-9:
                errors.append("ftm > fta")
            if vals["FG3M"] > vals["FGM"] + 1e-9:
                errors.append("fg3m > fgm")
            if vals.get("FG3A", 0) > vals["FGA"] + 1e-9:
                errors.append("fg3a > fga")
            implied = 2 * vals["FGM"] + vals["FG3M"] + vals["FTM"]
            if abs(implied - vals["PTS"]) > max(1.0, 0.06 * vals["PTS"]):
                warns.append(f"pts {vals['PTS']:.1f} differs from 2*FGM+3PM+FTM = {implied:.1f}")
        cv = _num(r, "uncertainty_cv", errors, required=False)
        results.append(
            RowResult(
                i,
                pid,
                mname,
                tuple(errors),
                tuple(warns),
                {**vals, "cv": cv if cv is not None else 0.15, "source": r.get("source") or "user_import"},
            )
        )
    dup = _duplicates(results)
    results = [replace(x, errors=(*x.errors, "duplicate player in file")) if x.player_id in dup else x for x in results]
    return ImportPreview("projections", cols, tuple(results), missing, tuple(notes))


def apply_projections(preview: ImportPreview, snapshot: Snapshot, label: str | None = None) -> Snapshot:
    """New snapshot with the imported per-game projections replacing the originals for matched players."""
    pg = snapshot.per_game.copy()
    sd = snapshot.per_game_sd.copy()
    src = list(snapshot.projection_source)
    n_applied = 0
    for r in preview.rows:
        if not r.ok or r.player_id is None:
            continue
        i = snapshot.index[r.player_id]
        for prim in PRIMITIVES:
            if prim in r.data:
                pg[i, PRIM_IDX[prim]] = float(r.data[prim])
        sd[i] = pg[i] * float(r.data["cv"])
        sd[i, PRIM_IDX["GP"]] = 10.0
        src[i] = f"import:{r.data['source']}"
        n_applied += 1
    new = replace(
        snapshot,
        snapshot_id=f"{snapshot.snapshot_id}-imp{content_hash(pg)[:6]}",
        label=label or f"{snapshot.label} + {n_applied} imported projections",
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        per_game=pg,
        per_game_sd=sd,
        projection_source=tuple(src),
        provenance={
            **snapshot.provenance,
            "imports": [*snapshot.provenance.get("imports", []), {"kind": "projections", "rows": n_applied}],
        },
    )
    problems = validate_snapshot(new)
    if problems:
        raise ValueError(f"import produced an incoherent snapshot: {problems}")
    return new


# --- eligibility -------------------------------------------------------------------------------


def preview_eligibility(text: str, snapshot: Snapshot) -> ImportPreview:
    cols, rows = parse_csv(text)
    missing = tuple(c for c in REQUIRED_ELIGIBILITY if c not in cols)
    results = []
    for i, r in enumerate(rows, start=1):
        errors: list[str] = []
        pid, mname, err = resolve_player(snapshot, r.get("player_id", ""), r.get("name", ""), r.get("espn_id", ""))
        if err:
            errors.append(err)
        raw = [
            p.strip().upper()
            for p in r.get("eligible_positions", "").replace("/", ";").replace(",", ";").split(";")
            if p.strip()
        ]
        bad = [p for p in raw if p not in PRIMITIVE_POSITIONS]
        if bad:
            errors.append(f"unknown positions {bad}; use PG SG SF PF C separated by ';'")
        if not raw:
            errors.append("eligible_positions empty")
        prim = r.get("primary_position", "").upper() or None
        if prim and prim not in PRIMITIVE_POSITIONS:
            errors.append(f"unknown primary_position {prim!r}")
        if prim and prim not in raw and not errors:
            errors.append("primary_position must be one of the eligible positions")
        results.append(
            RowResult(
                i,
                pid,
                mname,
                tuple(errors),
                (),
                {
                    "eligible_positions": sorted(set(raw)),
                    "primary_position": prim,
                    "source": r.get("source") or "import",
                    "effective_date": r.get("effective_date") or None,
                },
            )
        )
    dup = _duplicates(results)
    results = [replace(x, errors=(*x.errors, "duplicate player in file")) if x.player_id in dup else x for x in results]
    return ImportPreview(
        "eligibility",
        cols,
        tuple(results),
        missing,
        ("Imported eligibility is marked source=import and verified=False unless source starts with 'espn'.",),
    )


def apply_eligibility(preview: ImportPreview, snapshot: Snapshot) -> Snapshot:
    players = list(snapshot.players)
    n = 0
    for r in preview.rows:
        if not r.ok or r.player_id is None:
            continue
        i = snapshot.index[r.player_id]
        p = players[i]
        src = str(r.data["source"])
        players[i] = replace(
            p,
            eligible_positions=frozenset(r.data["eligible_positions"]),
            primary_position=r.data["primary_position"] or p.primary_position,
            eligibility_source=src,
            eligibility_verified=src.lower().startswith("espn"),
        )
        n += 1
    return replace(
        snapshot,
        players=tuple(players),
        snapshot_id=f"{snapshot.snapshot_id}-elig{n}",
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        provenance={
            **snapshot.provenance,
            "imports": [*snapshot.provenance.get("imports", []), {"kind": "eligibility", "rows": n}],
        },
    )


# --- ADP / ranks -------------------------------------------------------------------------------


def preview_adp(text: str, snapshot: Snapshot) -> ImportPreview:
    cols, rows = parse_csv(text)
    missing = tuple(c for c in REQUIRED_ADP if c not in cols)
    results = []
    platforms = set()
    for i, r in enumerate(rows, start=1):
        errors: list[str] = []
        warns: list[str] = []
        pid, mname, err = resolve_player(snapshot, r.get("player_id", ""), r.get("name", ""))
        if err:
            errors.append(err)
        adp = _num(r, "adp", errors, required=False, lo=1.0)
        rank = _num(r, "rank", errors, required=False, lo=1.0)
        if adp is None and rank is None:
            errors.append("adp or rank required")
        plat = r.get("platform", "").lower()
        if not plat:
            errors.append("platform required (e.g. espn, yahoo)")
        platforms.add(plat)
        if plat and plat != "espn":
            warns.append(f"{plat} ADP is not ESPN-specific; it is labeled and given wider uncertainty")
        results.append(
            RowResult(
                i,
                pid,
                mname,
                tuple(errors),
                tuple(warns),
                {"adp": adp, "rank": rank, "platform": plat, "as_of": r.get("as_of_date") or None},
            )
        )
    notes = ["Ranking is not ADP: imported ranks fill the rank column, ADP fills the survival/opponent model."]
    if len(platforms - {""}) > 1:
        notes.append(f"Mixed platforms in file: {sorted(platforms - {''})}; one platform per import is recommended.")
    return ImportPreview("adp", cols, tuple(results), missing, tuple(notes))


def apply_adp(preview: ImportPreview, snapshot: Snapshot) -> Snapshot:
    adp = snapshot.adp.copy()
    rank = snapshot.rank.copy()
    plats = set()
    n = 0
    for r in preview.rows:
        if not r.ok or r.player_id is None:
            continue
        i = snapshot.index[r.player_id]
        if r.data["adp"] is not None:
            adp[i] = r.data["adp"]
        if r.data["rank"] is not None:
            rank[i] = r.data["rank"]
        plats.add(r.data["platform"])
        n += 1
    plat = "+".join(sorted(plats)) if plats else snapshot.adp_platform
    return replace(
        snapshot,
        adp=adp,
        rank=rank,
        adp_platform=plat,
        snapshot_id=f"{snapshot.snapshot_id}-adp{n}",
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        adp_asof=max((r.data["as_of"] or "" for r in preview.rows if r.ok), default=snapshot.adp_asof)
        or snapshot.adp_asof,
        provenance={
            **snapshot.provenance,
            "imports": [
                *snapshot.provenance.get("imports", []),
                {"kind": "adp", "rows": n, "platforms": sorted(plats)},
            ],
        },
    )


# --- picks -------------------------------------------------------------------------------------


def preview_picks(
    text: str, snapshot: Snapshot, manager_ids: list[str], manager_names: dict[str, str] | None = None
) -> ImportPreview:
    cols, rows = parse_csv(text)
    missing = tuple(c for c in ["name"] if c not in cols)
    if "manager_id" not in cols and "manager_name" not in cols:
        missing = (*missing, "manager_id or manager_name")
    by_name = {normalize_name(v): k for k, v in (manager_names or {}).items()}
    results = []
    for i, r in enumerate(rows, start=1):
        errors: list[str] = []
        pid, mname, err = resolve_player(snapshot, r.get("player_id", ""), r.get("name", ""))
        if err:
            errors.append(err)
        mid = r.get("manager_id", "")
        if not mid and r.get("manager_name"):
            mid = by_name.get(normalize_name(r["manager_name"]), "")
        if mid not in manager_ids:
            errors.append(f"unknown manager {mid or r.get('manager_name')!r}")
        overall = _num(r, "overall", errors, required=False, lo=1.0)
        keeper = r.get("is_keeper", "").lower() in ("1", "true", "yes", "y")
        results.append(
            RowResult(
                i,
                pid,
                mname,
                tuple(errors),
                (),
                {
                    "manager_id": mid,
                    "overall": None if overall is None else int(overall),
                    "is_keeper": keeper,
                    "timestamp": r.get("timestamp") or None,
                },
            )
        )
    if all(r.data["overall"] is None for r in results):
        notes: tuple[str, ...] = ("No 'overall' column: rows are applied in file order as consecutive picks.",)
    else:
        notes = ("Rows are applied in ascending 'overall' order; gaps are rejected at commit.",)
    dup = _duplicates(results)
    results = [replace(x, errors=(*x.errors, "duplicate player in file")) if x.player_id in dup else x for x in results]
    return ImportPreview("picks", cols, tuple(results), missing, notes)


def picks_to_events(preview: ImportPreview) -> list[dict[str, Any]]:
    """Ordered pick_committed payloads for the batch endpoint (validation happens at commit)."""
    rows = [r for r in preview.rows if r.ok and r.player_id]
    if any(r.data["overall"] is not None for r in rows):
        rows = sorted(rows, key=lambda r: (r.data["overall"] is None, r.data["overall"] or 0))
    return [
        {
            "player_id": r.player_id,
            "manager_id": r.data["manager_id"],
            **({"overall": r.data["overall"]} if r.data["overall"] is not None else {}),
        }
        for r in rows
    ]


def _duplicates(results: list[RowResult]) -> set[str]:
    seen: dict[str, int] = {}
    for r in results:
        if r.player_id:
            seen[r.player_id] = seen.get(r.player_id, 0) + 1
    return {k for k, v in seen.items() if v > 1}


def template_text(kind: str) -> str:
    from app.settings import settings

    path = settings.data_dir / "templates" / f"{kind}_template.csv"
    return path.read_text()


def league_from_json(text: str) -> dict[str, Any]:
    from app.league.config import LeagueConfig

    data = json.loads(text)
    return LeagueConfig.model_validate(data).model_dump(mode="json")


def row_summary(preview: ImportPreview) -> str:
    return f"{preview.kind}: {preview.n_ok} ok, {preview.n_error} with errors" + (
        f", missing columns {list(preview.missing_columns)}" if preview.missing_columns else ""
    )


__all__ = [
    "ImportPreview",
    "RowResult",
    "Player",
    "np",
    "preview_projections",
    "apply_projections",
    "preview_eligibility",
    "apply_eligibility",
    "preview_adp",
    "apply_adp",
    "preview_picks",
    "picks_to_events",
    "template_text",
    "league_from_json",
    "row_summary",
]
