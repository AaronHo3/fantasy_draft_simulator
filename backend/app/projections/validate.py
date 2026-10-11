"""Retrospective holdout check of the baseline model on real seasons (labeled retrospective, not leak-free).

Fits on seasons before ``target`` and scores against the target season's actual per-game stats for
players with at least ``min_gp`` games. Compares against the naive last-season baseline and a small
grid of shrinkage / recency settings. Writes docs/VALIDATION.md.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.projections.baseline import BaselineConfig, evaluate_projection, naive_last_season, project_baseline
from app.settings import REPO_DIR

STATS = ("PTS", "REB", "AST", "STL", "BLK", "FG3M", "TOV", "FGA", "FTA", "MIN", "GP", "FG_PCT", "FT_PCT")


def _scaled(cfg: BaselineConfig, k_scale: float, weights: tuple[float, ...] | None = None) -> BaselineConfig:
    return replace(
        cfg,
        k_minutes={k: v * k_scale for k, v in cfg.k_minutes.items()},
        k_attempts={k: v * k_scale for k, v in cfg.k_attempts.items()},
        season_weights=weights or cfg.season_weights,
    )


def validate(data_dir: Path, target: str = "2025-26", min_gp: int = 20) -> dict:
    nd = Path(data_dir) / "nba" / "normalized"
    totals = pd.read_parquet(nd / "season_totals.parquet")
    espn = pd.read_parquet(nd / "espn_players.parquet")
    cw = pd.read_parquet(nd / "crosswalk.parquet")
    pos = pd.Series(
        {
            int(r.nba_id): p
            for r, p in zip(
                cw.itertuples(), cw["espn_id"].map(espn.set_index("espn_id")["primary_position"]), strict=True
            )
            if pd.notna(r.nba_id) and isinstance(p, str)
        }
    )
    seasons = sorted(totals["season"].unique())
    variants = {
        "naive_last_season": None,
        "baseline_default": BaselineConfig(),
        "baseline_k_x0.5": _scaled(BaselineConfig(), 0.5),
        "baseline_k_x2": _scaled(BaselineConfig(), 2.0),
        "baseline_w_0.7_0.3": _scaled(BaselineConfig(), 1.0, (0.7, 0.3, 0.0)),
        "baseline_w_0.4_0.4_0.2": _scaled(BaselineConfig(), 1.0, (0.4, 0.4, 0.2)),
    }
    results: dict[str, dict] = {}
    for name, cfg in variants.items():
        pred = naive_last_season(totals, target) if cfg is None else project_baseline(totals, target, pos, cfg).table
        results[name] = evaluate_projection(pred, totals, target, min_gp)
    report = {
        "target": target,
        "fit_seasons": [s for s in seasons if s < target],
        "min_gp": min_gp,
        "n_players": results["baseline_default"]["_n"]["players"],
        "results": results,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "caveat": "Retrospective: scored on players who actually played >= min_gp games in the target season "
        "(survivorship), with final rosters known; preseason ADP/eligibility of the target season were "
        "not used. Not a leak-free draft backtest.",
    }
    (REPO_DIR / "docs" / "VALIDATION.md").write_text(_render(report))
    return report


def _render(r: dict) -> str:
    lines = [
        "# Projection validation (retrospective)",
        "",
        f"Generated {r['generated_at']}. Target season {r['target']}, fit seasons {', '.join(r['fit_seasons'])}, "
        f"{int(r['n_players'])} players with >= {r['min_gp']} GP in the target season.",
        "",
        f"**Caveat.** {r['caveat']}",
        "",
        "## Mean absolute error of per-game projections (FG%/FT% attempt-weighted)",
        "",
        "| variant | " + " | ".join(STATS) + " |",
        "|---|" + "---|" * len(STATS),
    ]
    for name, res in r["results"].items():
        cells = []
        for s in STATS:
            v = res.get(s, {}).get("mae")
            cells.append("" if v is None else (f"{v:.3f}" if s in ("FG_PCT", "FT_PCT") else f"{v:.2f}"))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Mean bias (projection − actual)",
        "",
        "| variant | " + " | ".join(STATS) + " |",
        "|---|" + "---|" * len(STATS),
    ]
    for name, res in r["results"].items():
        cells = []
        for s in STATS:
            v = res.get(s, {}).get("bias")
            cells.append("" if v is None else (f"{v:+.3f}" if s in ("FG_PCT", "FT_PCT") else f"{v:+.2f}"))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Lower MAE is better. The default configuration is the one shipped in `BaselineConfig`; if a grid "
        "variant is clearly better on real data, update the default and record the change in DECISIONS.md.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    from app.settings import settings

    print(json.dumps(validate(settings.data_dir), indent=1, default=str)[:3000])
