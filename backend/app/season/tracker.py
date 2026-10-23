"""In-season tracker: actual category results per fantasy week from NBA game logs, for every team in a session.

Weeks are Monday-anchored (US date). Each team's weekly line sums its rostered players' real box scores;
with weekly lineups the top ``n_starting`` players by minutes that week are counted (the manager's actual
lineup is not known). Percentages are makes ÷ attempts. Nothing here touches projections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.draft.events import DraftState
from app.engine.categories import PRIM_IDX, PRIMITIVES, category_values, compare_categories, each_category_score, totals
from app.projections.snapshot import Snapshot

COLS = {
    "MIN": "min",
    "PTS": "pts",
    "REB": "reb",
    "AST": "ast",
    "STL": "stl",
    "BLK": "blk",
    "FG3M": "fg3m",
    "FG3A": "fg3a",
    "FGM": "fgm",
    "FGA": "fga",
    "FTM": "ftm",
    "FTA": "fta",
    "TOV": "tov",
}


def fetch_logs(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    """Live fetch of this season's game logs (one request). Regular season / playoffs go through the cached
    adapter; preseason (used only for testing the tracker before opening night) is fetched directly."""
    if season_type in ("Regular Season", "Playoffs"):
        from app.sources.nba_stats import fetch_game_logs

        return fetch_game_logs(season, season_type)
    from nba_api.stats.endpoints import playergamelogs

    raw = playergamelogs.PlayerGameLogs(
        season_nullable=season, season_type_nullable=season_type, timeout=60
    ).get_data_frames()[0]
    out = pd.DataFrame(
        {
            "nba_id": raw["PLAYER_ID"].astype(int),
            "game_id": raw["GAME_ID"].astype(str),
            "game_date": pd.to_datetime(raw["GAME_DATE"]).dt.date,
        }
    )
    for k, c in COLS.items():
        out[c] = raw[k].astype(float)
    return out


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_lines(logs: pd.DataFrame, nba_ids: dict[int, str]) -> pd.DataFrame:
    """Per (player, week) totals for rostered players. nba_ids: nba_id -> manager_id."""
    g = logs[logs["nba_id"].isin(list(nba_ids))].copy()
    if g.empty:
        return pd.DataFrame(columns=["nba_id", "manager_id", "week", "gp", *COLS.values()])
    dates = pd.to_datetime(g["game_date"]).dt.date
    g["week"] = [week_start(d).isoformat() for d in dates]
    g["manager_id"] = g["nba_id"].map(nba_ids)
    agg = (
        g.groupby(["nba_id", "manager_id", "week"])
        .agg(gp=("game_id", "nunique"), **{c: (c, "sum") for c in COLS.values()})
        .reset_index()
    )
    return agg


@dataclass(frozen=True)
class WeekResult:
    week: str
    team_totals: dict[str, np.ndarray]
    counted: dict[str, list[int]]  # manager -> nba_ids counted as starters


def week_results(lines: pd.DataFrame, week: str, managers: list[str], n_starting: int) -> WeekResult:
    team_tot: dict[str, np.ndarray] = {}
    counted: dict[str, list[int]] = {}
    wk = lines[lines["week"] == week]
    for m in managers:
        rows = wk[wk["manager_id"] == m].sort_values("min", ascending=False).head(n_starting)
        mat = np.zeros((len(rows), len(PRIMITIVES)))
        for k, c in COLS.items():
            mat[:, PRIM_IDX[k]] = rows[c].to_numpy(dtype=float)
        mat[:, PRIM_IDX["GP"]] = rows["gp"].to_numpy(dtype=float) if len(rows) else 0
        team_tot[m] = totals(mat) if len(rows) else np.zeros(len(PRIMITIVES))
        counted[m] = [int(x) for x in rows["nba_id"]]
    return WeekResult(week, team_tot, counted)


def standings_table(
    state: DraftState, snap: Snapshot, lines: pd.DataFrame, week: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(team table with category values + categories won vs the field, head-to-head grid) for one week."""
    league = state.league
    cats, tie = league.categories, league.tie_rule
    ids = [m.id for m in league.managers]
    names = {m.id: m.name.strip() for m in league.managers}
    wr = week_results(lines, week, ids, len(league.starting_slots))
    rows = []
    grid = pd.DataFrame(index=[names[m] for m in ids], columns=[names[m] for m in ids], dtype=float)
    for a in ids:
        vals = category_values(wr.team_totals[a], cats)
        scores = []
        for b in ids:
            if a == b:
                continue
            sc = each_category_score(compare_categories(wr.team_totals[a], wr.team_totals[b], cats, tie), tie)
            grid.loc[names[a], names[b]] = sc
            scores.append(sc)
        rows.append(
            {
                "team": names[a],
                "games_counted": int(wr.team_totals[a][PRIM_IDX["GP"]]),
                "players_counted": len(wr.counted[a]),
                **{
                    c.key: (
                        round(vals[c.key], 3)
                        if vals[c.key] is not None and c.kind.value == "ratio"
                        else (None if vals[c.key] is None else round(vals[c.key]))
                    )
                    for c in cats
                },
                "FGA": int(wr.team_totals[a][PRIM_IDX["FGA"]]),
                "FTA": int(wr.team_totals[a][PRIM_IDX["FTA"]]),
                "avg_cats_won_vs_field": round(float(np.mean(scores)), 2) if scores else None,
            }
        )
    df = pd.DataFrame(rows).sort_values("avg_cats_won_vs_field", ascending=False)
    for c in cats:
        df[f"rank_{c.key}"] = df[c.key].rank(ascending=not c.higher_is_better, method="min")
    return df, grid
