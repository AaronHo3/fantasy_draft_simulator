# Data sources

Every source below lists what was actually verified in this repository, when, and how. "Verified"
means a request was made from this machine with the adapter or client named and the response shape
was inspected. Anything else is marked planned or unverified.

## Summary table

| Field | Primary source | Fallback | Status (2026-10-09) |
|---|---|---|---|
| Active NBA player universe | nba_api `commonallplayers` (2026-27) | ESPN players endpoint, CSV | verified, 622 rows, 0.2 s |
| Season totals (3 completed seasons) | nba_api `leaguedashplayerstats` Totals | CSV | verified 2025-26, 582 rows, 0.3 s |
| Game logs | nba_api `playergamelogs` (one call/season) | CSV | verified 2025-26, 26,651 rows, 0.9 s |
| ESPN eligibility (eligibleSlots, primary pos) | ESPN public `players` endpoint, season 2027 | eligibility CSV, manual override | verified, 1,095 active players, no cookies |
| ESPN ADP / % owned / auction value | same (`ownership`) | ADP CSV (platform-labeled) | verified, ADP dated 2026-10-09 |
| ESPN draft ranks (STANDARD, ROTO) | same (`draftRanksByRankType`) | — | verified |
| ESPN projected season totals | same, stat split `102027` (statSourceId=1) | local baseline projection | verified for 349 players |
| Prior-season ESPN totals | same, split `002026` | nba_api | verified, 1,102 players |
| Injury status | same (`injuryStatus`: ACTIVE/DAY_TO_DAY/OUT) | manual notes | verified; a designation is not an absence forecast |
| NBA schedule 2026-27 by fantasy day | ESPN `view=proTeamSchedules_wl`, season 2027 | generic games/week assumption | verified, 1,200 games, 2026-10-20..2027-04-12, scoring periods 1..174 |
| NBA CDN schedule | `cdn.nba.com/.../scheduleLeagueV2_1.json` | — | blocked from this network (non-JSON response) |
| Private ESPN league settings / draft | `espn_api` League with SWID/espn_s2 (optional) | manual config, picks CSV | implemented read-only import; unverified against a real league from here (no credentials) |
| Live ESPN draft feed | — | manual entry | NOT supported (never validated) |

## nba_api (stats.nba.com)

- Package: `nba_api==1.11.4`. Client default headers are required; ad-hoc HTTP hangs on this
  network (Akamai). Timeouts 30–60 s, 3 bounded retries with exponential backoff and jitter.
- Endpoints used (all league-wide, one request per season):
  - `commonallplayers(is_only_current_season=1, season="2026-27")`: PERSON_ID, DISPLAY_FIRST_LAST,
    TEAM_ID, TEAM_ABBREVIATION, FROM_YEAR, TO_YEAR, ROSTERSTATUS.
  - `leaguedashplayerstats(season, per_mode_detailed="Totals")`: PLAYER_ID, PLAYER_NAME, TEAM_ID,
    TEAM_ABBREVIATION, AGE, GP, MIN, FGM, FGA, FG3M, FG3A, FTM, FTA, OREB, DREB, REB, AST, TOV,
    STL, BLK, PTS, TEAM_COUNT (>1 means traded; the row is the season aggregate).
  - `playergamelogs(season_nullable, season_type_nullable="Regular Season")`: per game rows with
    GAME_ID, GAME_DATE, MATCHUP, MIN, and the same counting primitives. Postseason is fetched
    separately with `season_type_nullable="Playoffs"` and stored separately.
- Units: counting stats are totals; MIN is minutes (float). Percentages are recomputed from
  makes/attempts, never taken from the source.
- Seasons fetched by `make refresh`: 2023-24, 2024-25, 2025-26 (completed) and 2026-27 player
  universe. Raw JSON is cached under `data/nba/raw/nba_api/<endpoint>/<season>.json` with the
  retrieval timestamp and content hash; normalized parquet under `data/nba/normalized/`.
- Terms: public endpoints used at low volume (≈ 8 requests per full refresh). No scraping of
  nba.com pages.

## ESPN fantasy public read endpoints (lm-api-reads.fantasy.espn.com)

- Base: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{seasonId}`.
- `seasonId` = NBA season end year (2027 for 2026-27). Verified via schedule dates.
- `/players?view=kona_player_info&scoringPeriodId=0` with header
  `x-fantasy-filter: {"players":{"filterActive":{"value":true},"limit":2000,
  "filterStatsForTopScoringPeriodIds":{"value":2,"additionalValue":["002027","102027","002026"]},
  "sortDraftRanks":{"sortPriority":100,"sortAsc":true,"value":"STANDARD"}}}`.
  Response: list of player objects. Fields used: `id` (ESPN player id), `fullName`,
  `defaultPositionId` (1=PG,2=SG,3=SF,4=PF,5=C; -1/0 unknown), `eligibleSlots` (0-indexed slot
  ids; 0 PG,1 SG,2 SF,3 PF,4 C,5 G,6 F,7 SG/SF,8 G/F,9 PF/C,10 F/C,11 UTIL,12 BE,13 IR),
  `proTeamId` (ESPN team id; map in adapter), `injuryStatus`, `injured`, `active`,
  `ownership.averageDraftPosition`, `ownership.percentOwned`, `ownership.auctionValueAverage`,
  `ownership.date` (ms epoch), `draftRanksByRankType.{STANDARD,ROTO}.rank`,
  `stats[]` with `id` = `{statSourceId}{statSplitTypeId}{seasonId}`: `102027` = ESPN projection
  for 2026-27 season totals, `002026` = actual 2025-26 totals, `0540...` = single game splits.
  Stat keys: 0 PTS, 1 BLK, 2 STL, 3 AST, 6 REB, 11 TO, 13 FGM, 14 FGA, 15 FTM, 16 FTA, 17 3PM,
  18 3PA, 19 FG%, 20 FT%, 40 MIN, 42 GP.
- `/players?view=players_wl` (lighter, 1,095 rows) is used as the fast eligibility refresh.
- `?view=proTeamSchedules_wl` on the season root returns `settings.proTeams[].proGamesByScoringPeriod`
  with game `date` (ms), `homeProTeamId`, `awayProTeamId`, `scoringPeriodId`.
- Response size ≈ 24 MB for kona_player_info; cached raw with hash; refreshed at most daily.
- Access: no cookies needed for these views. Private league views (`mSettings`, `mDraftDetail`)
  need `SWID` and `espn_s2` cookies via `backend/.env` and are optional.
- Caveat: undocumented endpoint used by ESPN's own web client; schema validated on every fetch,
  failures fall back to the last snapshot.

## ESPN league read endpoint (public leagues, no cookies) — verified 2026-10-19

- `GET /apis/v3/games/fba/seasons/{seasonId}/segments/0/leagues/{leagueId}` with
  `view=mTeam&view=mRoster&view=mSettings&view=mMatchup&view=mSchedule&view=mTransactions2&view=mStatus`
  (adapter: `backend/app/sources/espn_league.py`; service: `backend/app/season/service.py`).
- Works without cookies only when the league is set to "Make League Viewable to Public"
  (League → Settings → Basic Settings). A private league answers HTTP 401 → `LeagueAccessError`
  → API 409 `league_private` with that instruction. Cookies are not used by this path.
- Verified on league 2075231076 (13 teams) from this machine, HTTP 200: `settings` (name,
  `scoringSettings.scoringType=H2H_CATEGORY`, `scoringItems[].statId` 0/1/2/3/6/17/19/20,
  `rosterSettings.lineupSlotCounts`, `positionLimits` ("5": 4 = max 4 C), `lineupLocktimeType`),
  `status.currentMatchupPeriod`, `members[]` (id, firstName, lastName), `teams[]` (id, name,
  owners, primaryOwner, record, `roster.entries[]` with `playerId`, `lineupSlotId` (13 = IR),
  `injuryStatus`, `acquisitionType`, `playerPoolEntry.player.{id,fullName,proTeamId}`),
  `schedule[]` (id, matchupPeriodId, home/away `{teamId, cumulativeScore.scoreByStat{statId:
  {score,result}}}`; `away` absent on a bye week), `transactions[]` (type DRAFT / ROSTER / WAIVER /
  FREEAGENT / FUTURE_ROSTER / TRADE_ACCEPT, status EXECUTED / CANCELED / FAILED_*, `items[]` with
  type ADD / DROP / LINEUP / DRAFT / TRADE, playerId, fromTeamId, toTeamId, `proposedDate` ms).
- Live weekly category scores (`schedule[].home/away.cumulativeScore.scoreByStat`) come from the
  `mMatchup` view; requesting `mSchedule` alongside it replaces that schedule with an unscored copy, so
  `mSchedule` is not requested (verified 2026-10-21 after the first games). `cumulativeScore` lags
  the site by hours; the `mMatchupScore` view adds `cumulativeScoreLive` (wins/losses/ties and
  `scoreByStat`), which is what ESPN's matchup page shows, and the parser prefers it when present
  (verified 2026-10-21: cumulativeScore said 7-1-0 while the site and cumulativeScoreLive said 6-2-0).
- The default `mRoster` view is the roster as it stood when the current scoring period (day)
  opened: an add/drop executed today appears only under `?view=mRoster&scoringPeriodId=<current+1>`
  (verified 2026-10-20 with an executed FREEAGENT transaction missing from the default view). The
  fetch therefore makes a second request for the next period's rosters and merges them in; on failure
  it keeps the default view.
- All 171 rostered player ids resolved to snapshot players through `espn_id`; unknown ids are kept
  as owned placeholders `espn:<id>` (no projection) so they never appear as free agents.
- Sync also refreshes `/players?view=kona_player_info` (above) for live injury status and
  percent owned; written to `data/nba/live/<league_id>/players.parquet` (gitignored). The raw league
  payload is cached at `data/nba/live/<league_id>/league.json` so results survive a restart.
- Matchup periods are Monday-anchored weeks; period 1 = 2026-10-20..2026-10-25 and period 18 is
  doubled for the All-Star break (2027-02-15..02-28), which makes the 22-period calendar end on
  ESPN's `status.finalScoringPeriod` 160 = 2027-03-28 (`backend/app/season/weeks.py`,
  `calendar_matches_espn`; sync warns if ESPN's final period ever disagrees). ESPN's
  `matchupPeriods` map returned singletons, so the calendar is derived, not read. The schedule
  parquet also has no games from Dec 3 to Dec 12 (NBA Cup knockout games are not scheduled yet),
  so period 8 game counts will be low until `make refresh` after the Cup bracket is set.

## espn_api (community client, `espn_api==1.0.1`)

Inspected `espn_api/basketball/constant.py`, `league.py`, `player.py`, `requests/espn_requests.py`
for slot ids, stat ids, pro-team ids, and the `players_wl` / `kona_player_info` views. Used for
the optional private-league import only; the public adapter uses httpx directly to control
timeouts, retries, and caching.

## User-provided CSV imports

Templates in `data/templates/`. Units are stated in each header row. See USER_GUIDE.md.

## Papers reviewed for methodology (not implemented verbatim)

- arXiv 2409.09884 (dynamic player value for fantasy basketball) and arXiv 2307.02188
  (improving fantasy basketball algorithms). The brief forbids claiming H- or G-scoring without
  implementing the exact definitions; this project uses the documented simpler approach in
  MODEL_CARD.md.

## Verified refresh (2026-10-09, local; 2026-10-10T01:43Z)

Run from this machine with `cd backend && uv run python -c "from pathlib import Path; from
app.sources.refresh import refresh_all; print(refresh_all(Path('../data')))"` after the Phase 2
adapters landed (`backend/app/sources/`, `backend/app/identity/crosswalk.py`). 13/13 steps ok
(12 HTTP requests + the local crosswalk), 5.3 s wall clock, no credentials, nothing kept from a
previous run. Raw cache 61 MB under `data/nba/raw/`, normalized parquet 1.8 MB under
`data/nba/normalized/` (both gitignored).

| Table (parquet) | Rows | Fetch duration | fetched_at (UTC) | Notes |
|---|---|---|---|---|
| players | 622 | < 1 s | 2026-10-10T01:43:25 | nba_api `commonallplayers` 2026-27 |
| season_totals | 1,723 | ≈ 1 s total (3 calls) | 2026-10-10T01:43:26 | 572 + 569 + 582 rows for 2023-24, 2024-25, 2025-26 Regular Season; `team_count>1` marks traded players |
| game_logs | 84,768 | ≈ 3 s total (6 calls) | 2026-10-10T01:43:27..29 | RS 26,401 / 26,306 / 26,651; Playoffs 1,685 / 1,804 / 1,921 |
| espn_players | 1,095 | ≈ 1 s (24.4 MB) | 2026-10-10T01:43:30 | active players only; 348 with projection split `102027`, 558 with `002026` totals, 1,095 with ADP (`ownership.date` 2026-10-09/10) |
| schedule | 1,200 | < 1 s | 2026-10-10T01:43:30 | 2026-10-20 .. 2027-04-12, scoring periods 1..174, NBA tricodes |
| crosswalk | 1,169 | local | — | 547 `name_team` + 1 `name_unique` links, 74 `nba_only`, 547 `espn_only` |

Per-call timestamps are second-resolution in this run (later runs record milliseconds), so the
durations above are upper bounds.

Identity resolution: 621 unresolved records (`data/nba/normalized/unresolved.json`), all reason
`no_candidate`; no ambiguous names occurred in either source.
- 74 `nba_only`: NBA 2026-27 universe rows without any active ESPN record, e.g. AK Okereke (LAL),
  Alex Morales (ORL), Alpha Diallo (DEN), Andrew Holifield (OKC), Arthur Kaluma (LAL). These are
  training-camp / two-way profiles; their ESPN eligibility is therefore unverified and they are
  counted as `missing_eligibility` in `health.json` (never substituted from NBA positions).
- 547 `espn_only`: ESPN marks many non-roster players `active=true` (199 with `proTeamId` 0 and
  348 with a stale team), e.g. Adreian Payne (ORL), Sim Bhullar (SAC), Phil Pressey (GSW). They
  carry ESPN's default ADP of ≈ 139.98 and almost never a projection (345 of the 348 projected
  players are linked to an NBA id). They are kept in `espn_players.parquet` but have no NBA id.

Observed source quirks recorded for the adapters:
- The `filterActive` filter in `x-fantasy-filter` is not applied server-side: the response holds
  3,207 players, of which 1,095 have `active=true`; `parse_players` keeps only those.
- `002027` (current-season actual split) is present with an empty `stats` object before the
  season starts; the parser treats an empty split as absent.
- ESPN's schedule view uses web abbreviations (`NO`, `GS`, `NY`, `SA`, `UTAH`, `WSH`, `PHI`,
  `PHX`) while `espn_api.PRO_TEAM_MAP` uses `NOP`, `GSW`, `NYK`, `SAS`, `UTA`, `WAS`, `PHL`,
  `PHO`; `app/sources/teams.py` folds both into NBA tricodes by `proTeamId`, and a test asserts
  equality with the installed `espn_api` map.
