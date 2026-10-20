# Decisions

Format: `DEC-nn` — date — decision — rationale — limitations.

## DEC-01 — 2026-10-09 — Standalone greenfield app in this repository
The working directory was empty. A sibling NBA analytics repo exists on this machine but the brief
forbids assuming access to another repository, so this app is self-contained. Its own adapters
fetch NBA data. Limitation: no reuse of the sibling's 2.2 GB cache; a CSV/parquet import path
exists if the user wants to feed it in later.

## DEC-02 — 2026-10-09 — Python 3.12 via uv, FastAPI, NumPy/pandas/SciPy, SQLite, Parquet
Python 3.14 is the system default but 3.12 has the broadest wheel coverage for the scientific
stack. uv pins everything in `uv.lock`. Frontend: Vite + React 19 + TypeScript, zustand for
state. No Redis/K8s/cloud. Limitation: single-user, single-process.

## DEC-03 — 2026-10-09 — ESPN public player endpoint is the eligibility/ADP/projection source
Verified (see DATA_SOURCES.md): `lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/2027/players`
with `view=kona_player_info` and an `x-fantasy-filter` header returns, without cookies, 1,095
active players with `eligibleSlots`, `defaultPositionId`, `ownership.averageDraftPosition`,
`draftRanksByRankType`, injury status, and ESPN's own projected season totals (stat split id
`102027`, statSourceId 1) for 349 players. This is the only accessible ESPN-specific eligibility
and ADP, so it is the primary source for both. Limitation: undocumented endpoint, can change
without notice; raw responses are cached so a failure never destroys the last snapshot.

## DEC-04 — 2026-10-09 — ESPN seasonId = NBA season end year
`seasons/2027` schedule starts 2026-10-20 and ends 2027-04-12, so ESPN 2027 == NBA `2026-27`.
Encoded as `espn_season_id("2026-27") == 2027` with a test.

## DEC-05 — 2026-10-09 — Schedule from ESPN proTeamSchedules, not NBA CDN
`cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json` returned non-JSON (blocked) from this
network, while ESPN's `view=proTeamSchedules_wl` returned all 1,200 regular-season games keyed by
`scoringPeriodId` (fantasy day), which is exactly the unit the lineup model needs.

## DEC-06 — 2026-10-09 — nba_api with its default headers; league-wide endpoints only
`commonallplayers`, `leaguedashplayerstats` (Totals) and `playergamelogs` return a whole season in
one request each (~0.3–1 s). Per-player endpoints are not used. Hand-rolled HTTP to
stats.nba.com hangs on this network; nba_api's header set is required.

## DEC-07 — 2026-10-09 — Default scoring preset: H2H Most Categories, with a confirm banner
Per the brief. The format is a required field; the UI shows a persistent "confirm your scoring
format" state until the user acknowledges it. Each-category and roto have separate objectives.

## DEC-08 — 2026-10-09 — Three recommendation layers, fast layer always authoritative fallback
Layer A (vectorized screening) answers every request synchronously. Layers B/C run as bounded
background jobs and only replace Layer A output when their revision ids match the current state.

## DEC-09 — 2026-10-09 — Projection default = blend of local baseline and ESPN projection
Where an ESPN projection exists the default projection is a weighted blend (weights in
MODEL_CARD.md, user-adjustable); otherwise the local baseline alone. Both are stored separately
with provenance; the UI shows which was used. Limitation: ESPN projections cover only ~350
players; blend weights were chosen by the retrospective check described in MODEL_CARD.md, which is
not a leak-free backtest.

## DEC-10 — 2026-10-09 — Lineup legality via assignment problem
Player-to-slot legality is solved with `scipy.optimize.linear_sum_assignment` on a bipartite cost
matrix (players x slots, infeasible pairs = large cost). This handles multi-eligibility correctly
(a player fills one slot). Daily collision modeling uses the same solver per scoring period under
a game-count cap. Primary-position caps are enforced as a separate counting constraint.

## DEC-11 — 2026-10-09 — Robust standardization over a fantasy-relevant pool
Category z-values use the pool of the top `managers * roster_size * 1.2` players ranked by an
unweighted first-pass value, with median/MAD scale (configurable to mean/std). Percentages are
standardized as volume-weighted impact (`FGM - b*FGA`) where `b` is the pool's aggregate rate.

## DEC-12 — 2026-10-09 — Correlated weekly simulation via shared latent factors
Per-player weekly outcomes = games_played (binomial with availability rate) x per-game stats with
a shared "minutes/usage" latent factor per player per week (lognormal) so categories move
together; shooting makes are binomial given attempts and a beta-shrunk rate. Documented as a
modeling choice, not calibrated on real weekly variance yet.

## DEC-13 — 2026-10-09 — ESPN ADP values ≥ 139 are treated as missing
The public endpoint reports `averageDraftPosition` ≈ 139.9–140.4 for every player without real draft data
(1,095 of 1,095 active players carry a value; only ~153 are below 139). Values ≥ 139.0 are stored as
NaN in the snapshot (`ADP_PLACEHOLDER_MIN`), so survival hints and the opponent model only use real ADP.
Limitation: a genuinely late-drafted player with true ADP 139+ is treated as undrafted.

## DEC-14 — 2026-10-09 — Replacement horizon = the user's *following* pick
Layer A's value-above-replacement compares a candidate with the best compatible player expected to still
be available at the user's next decision after this one (picks by other managers before the following
turn). Comparing against "best available right now" made every non-top candidate negative and ignored
opportunity cost. Survival hints still use the distance to the user's next turn.

## DEC-15 — 2026-10-09 — Baseline shrinkage weakened and recency increased after real validation
`make validate` (docs/VALIDATION.md) on the 2025-26 holdout (fit on 2023-24 and 2024-25; 383 players with
≥ 20 GP) showed the initial constants over-shrunk: k×0.35–0.5 beat k×1 on every category and recency
0.7/0.3 beat 0.55/0.30/0.15. Defaults are now k_minutes = 140 (STL/BLK 280), k_attempts FG 105 / FT 52 /
FG3 70, weights 0.6/0.3/0.1. The third-season weight is a judgment call (only two fit seasons existed);
the holdout is a single season, so these are indicative, not tuned to the decimal.

## DEC-16 — 2026-10-09 — Player universe for the real snapshot
NBA active-roster players (nba_api `commonallplayers`) plus ESPN active players with a pro team; ESPN
profiles without a team (199, mostly retired/overseas) are excluded. 970 players result. Players
without NBA history use the ESPN projection when present, else a rank-tiered minutes prior with
position-group rates and a 35 % coefficient of variation, labeled `prior`.

## DEC-17 — 2026-10-10 — Defaults set to the user's actual league
Per the user: H2H each category with ties allowed (a tied category counts half, the ESPN W-L-T
convention; selectable as zero in setup), 12 managers, 13-player rosters (10 starters PG/SG/SF/PF/C/
G/F/UTIL×3, 3 bench, 1 IR), no position limits except a maximum of 4 centers (ESPN primary position),
weekly lineups, snake draft. The draft position is unknown until draft day, so the draft screen's top
strip has a "My team" selector that sends `league_updated` and recomputes the schedule, replacement
horizon and recommendations. The objective for this format is the expected number of categories won
per weekly matchup; the 4-center cap is enforced in Layer A (flag + penalty) and in every rollout for
every manager.

## DEC-18 — 2026-10-10 — Fast ranking is the primary recommendation; refined layer is supplementary
`make evaluate` (docs/EVALUATION.md): 120 paired mock drafts per strategy on the 2025-26 holdout.
The fast ranking beat the opponents' value-order bot by +0.53 categories per matchup (SE 0.13,
79 better / 34 worse) and the naive last-season approach by about one category, but was not
distinguishable from drafting by projected value alone (+0.06, SE 0.06). The refined simulation
layer at a 2 s budget was not better than the opponents' bot (−0.32, SE 0.31, 20 drafts). Decision:
keep the shortlist ordered by the fast score, present the refined columns as supplementary and
label them as not yet validated, and treat the projection model (the component that carried the
result) as the thing to improve first. Follow-up at an 8 s budget (docs/EVALUATION_refined_8s.md, 5 seats × 4 seeds): refined −0.14 ± 0.29
vs the bot and −0.01 ± 0.27 vs projected value; depth does not rescue it. The refined layer stays
supplementary and is a candidate for removal from the default flow if a later experiment with ADP-based
opponents and more seeds does not show a gain.

## DEC-19 — 2026-10-10 — Learned (ridge) projections replace the hand-tuned baseline as the default source
Six seasons of history (2020-21 onward) were fetched. `app/projections/learned.py` fits a ridge regression
per stat on real year-to-year transitions (features: last two seasons' per-game and per-minute numbers,
minutes over the last 25 games, games history, age, team change; penalty chosen on the latest training
transition; only transitions whose target precedes the projection year are used). docs/PROJECTION_RESEARCH.md:
rank correlation with realized fantasy value 0.754 vs 0.718 (2024-25) and 0.660 vs 0.644 (2025-26) for the
baseline, better minutes/games error on both. Draft edge measured model-vs-model (my seat on ridge, opponents
on the baseline, 120 paired drafts per year, docs/EVALUATION_model_vs_model_*.md): +1.07 ± 0.11 categories
per matchup in 2025-26 but −0.07 ± 0.08 in 2024-25. The ranking gain is consistent; the draft gain is not,
so the edge is real but year-dependent and should be re-checked as seasons are added. The real snapshot now
uses ridge for every player with a feature season (baseline fallback otherwise), still blended 50/50 with
ESPN's projection where one exists.

## DEC-20 — 2026-10-10 — Rich ensemble becomes the default; games played stays in, projected not raw
Extended the learned model with role features (share of games at ≥ 28 / ≥ 20 minutes, last-10-game
minutes, games missed, playoff minutes) and a gradient-boosted variant; "ens" averages ridge and GBM on the
rich features. Ranking quality (docs/PROJECTION_RESEARCH.md): ens 0.763 / 0.655 vs plain ridge 0.754 / 0.660
on 2024-25 / 2025-26 (a wash). Draft edge model-vs-model: ens +0.16 / +0.59 (both years positive,
66–54 and 77–40), ridge −0.07 / +1.07 (higher mean, one losing year), mix −0.11 / +0.86. Ens is the
default because it never lost a year; the margins are inside noise and this should be revisited with a
third holdout. Games played: the model's shrunk projection beats flat, three-year-average and
last-season sources on ranking quality in both years (docs/GAMES_PLAYED_ABLATION.md); last-season GP is
harmful in both drafts and both rankings. Kept the projected GP in season value.

## DEC-21 — 2026-10-10 — Four holdout seasons: the ensemble is confirmed as the default
History now spans 2016-17..2025-26 (10 seasons; 2019-20 and 2020-21 games played are scaled to an
82-game pace, `learned.normalize_games`). Ranking quality (Spearman vs realized fantasy value) on four
holdouts, ens vs ridge vs baseline: 2022-23 0.740 / 0.727 / 0.720; 2023-24 0.784 / 0.770 / 0.775;
2024-25 0.759 / 0.753 / 0.718; 2025-26 0.659 / 0.658 / 0.644. The ensemble is first in every year.
Paired draft edge vs the same seat drafting on the baseline (120 drafts each, SE ≈ 0.1):
ens +0.06 / +0.81 / +0.01 / +0.65 (mean +0.38, never negative); ridge −0.63 / +0.36 / +0.03 / +0.87
(mean +0.16). The ensemble stays the default; the snapshot is rebuilt on ten seasons of training data.
Caveat: holdout universes contain only players with a current ESPN link, so older years lose retired
players; opponents still draft by value order rather than real ADP.

## DEC-22 — 2026-10-10 — Roster-aware (diminishing-returns) weighting tested and left off
Hypothesis: in H2H each category, +1 z is worth more in a category near the line than in one the
roster already dominates, so the fast ranking should scale each category by exp(-(T/s)²/2) where T is
the roster's category z-total. Implemented (`Strategy.roster_aware`, `roster_scale`) and tested in
paired drafts against the plain ranking (docs/EVALUATION_roster_aware_*.md, 120 drafts per cell, Δ
categories won per matchup vs projected value): s = 3.6 → −1.23 / +0.15 / −0.15 / −0.25 (2025-26 /
2024-25 / 2023-24 / 2022-23); s = 8 → −0.20 / +0.04 (two worst years); s = 14 → +0.01 / +0.05.
Reading: over a draft's range the category win probability is close to linear in value because
weekly category margins are noisy relative to a roster's total; discounting strong categories mostly
makes the drafter pass on the best available player. Total value wins. Default is off; the option and
the per-category marginal values remain available for inspection.

## DEC-23 — 2026-10-13 — Rookie discount and returning-from-lost-season adjustment
Preseason games are not ingested (bench-unit minutes, rested starters; low signal). Two groups the learned
model cannot see are adjusted in the snapshot build instead:
- **Rookies with no NBA history** (ESPN projection only): counting stats and minutes × 0.85, games capped at
  65, cv 0.35, source `espn_rookie_discounted`. Judgment call, not validated (ESPN's past rookie projections
  are not retrievable). Caleb Wilson moved from 29th to the mid-rounds, near his ADP.
- **Players with history who played zero games last season**: 22 such returns 2017-2025 (≥ 1,000 minutes
  the year before) produced a median 0.75× the baseline's projected per-game value, 0.85× minutes and 0.76×
  games on return; stars (Durant, Murray, Leonard, Porziņģis, Zion) matched or beat the per-game projection
  but still lost games, role players collapsed. Split by role in the last played season: stars (≥ 30 mpg, n=7: Durant, Wall, Bridges,
  Murray, Porziņģis, Bey, Porter) returned to a median 100 % / mean 94 % of projected games (71 % reached 60+,
  only Durant at 32 fell under 45) and 112 % of projected per-game value; role players (n=15) to 60 % of games
  and 56 % of per-game value. Applied: stars games × 0.94, rates × 1.0; role players games × 0.62, rates × 0.75
  (shrunk toward 1 for the small sample); uncertainty × 2 for both; source suffix `_returning`. Caveat: injury
  type is not in the data; the two Achilles returns among stars (Durant 0.57, Wall 0.78) were the worst, so an
  Achilles case like Haliburton may sit below the star average. The ridge/ensemble has no feature row for these players (they fall back to
  the baseline + ESPN blend), which is why the adjustment lives in the build.
Players with a short last season (Kessler 5 GP, Tatum 16 GP) need no special case: their games-played
history already pulls the learned model's availability projection down (56 and 62 games).
