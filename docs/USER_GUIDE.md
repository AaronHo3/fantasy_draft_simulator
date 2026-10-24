# User guide

## Setup

Requirements: Python 3.12 (uv installs it), Node 24, no accounts, no ESPN credentials.

```
make install                 # backend: uv sync; frontend: npm ci
make dev                     # backend http://127.0.0.1:8000, frontend http://127.0.0.1:5173
make dev BACKEND_PORT=8020 FRONTEND_PORT=5180   # if those ports are taken
```

Open the frontend URL. The **Setup** screen lets you:

- pick a **data snapshot**: the real `NBA 2026-27` snapshot (if `make refresh` + `make build-snapshot`
  have been run) or the synthetic demo (always available, loudly labeled);
- choose which categories are scored (ESPN 9-cat, 8-cat without turnovers, or any subset by
  toggling chips); only scored categories enter rankings, simulations, the category profile and
  the performers' contribution, and unscored stats are labelled as such wherever they still appear;
- set the scoring format (H2H each category, H2H most categories, rotisserie), lineup mode
  (weekly / daily), strict eligibility, managers and draft order (snake, linear, third-round
  reversal), your team, starting slots, bench / IR counts, primary-position caps, keepers and
  traded picks; or paste a full league JSON (advanced);
- tick **Confirm your scoring format**. Until it is confirmed the draft screen shows a warning and
  every recommendation carries a note, because the objective depends on it.

Create the session; the URL now carries `?session=<id>` and the id is also kept in the browser, so
reloading or reopening the tab restores it. The Setup screen lists existing sessions to resume.

## The interface

The app is a single workspace: a charcoal sidebar on the left (Setup, Draft, Season, Performers,
Recap, Data health; Season and Performers appear once the draft is complete) with the open session,
linked league and last sync pinned at the bottom, and a page on the right with its title, context
chips (league, week, data source) and that page's own filters directly under the title. Page
selections such as the Season tab, the Performers team/week and the matchup period are kept in the
URL hash, so a reload or a shared link lands on the same view. Under 1180 px the sidebar collapses
to an icon rail; on a phone it becomes a bottom tab bar.

Colour has one meaning everywhere: teal is an action or a selection, amber marks what is yours
(your picks, your column, the team on the clock), green/red mark favoured/unfavoured and above/below
expectation, grey and hatched fills are projections, and NBA team colours identify players in
portraits, marks and charts. Every chart writes its exact value next to the bar, cell or point, so
colour is never the only signal; hover or focus any bar, cell or point for the value and its unit.
A "How this works" section at the bottom of Draft and Season shows the flow from projections and
rosters to simulated weeks and recommendations.

Demo data is labelled in the sidebar, in the draft status strip and in the page chips; nothing in
the UI blends it with a real snapshot.

## Data refresh

```
make refresh          # ~12 requests: nba_api (3 seasons totals + game logs, active players), ESPN players + schedule
make build-snapshot   # baseline projections + ESPN projections/eligibility/ADP -> data/nba/snapshots/<id>/
make validate         # retrospective holdout check of the baseline model -> docs/VALIDATION.md
make health           # data health JSON (sources, timestamps, coverage, unresolved identities)
```

Nothing is fetched while you draft. A failed refresh keeps the previous snapshot; the Data health
screen shows per-source status, fetch timestamps, player coverage, missing eligibility and
unresolved identities. The snapshot label and ADP date are shown in the draft top strip.

## Draft day workflow

1. Start `make dev`, open the session, confirm the format if you have not. When the draft order is
   revealed, pick your slot in the **My team** selector in the top strip (it can be changed at any
   time; the schedule and every recommendation recompute for that slot).
2. The top strip shows round, overall pick, the manager on the clock, your next pick and the
   number of picks until it, save status, snapshot date, scoring format and the model tier that
   produced the current recommendations (A fast / B / C refined with elapsed time).
3. When **another manager picks in ESPN**, record it: press `/`, type part of the name (accents and
   suffixes are ignored, team codes work), move with `↑`/`↓`, press `Enter` to select, check the
   team in the inline bar (it defaults to the team on the clock; the server rejects picks for
   anyone else), press `Enter` again to record. Position chips and the availability filter narrow
   the list. Availability, rosters, the scoreboard and the recommendations update immediately;
   the save badge returns to "saved" when the backend has stored the event. The row buttons in
   the Recommendations and All players tables record the pick for whoever is on the clock in one
   click; when it is your turn they read "Draft".
4. When **you are on the clock**, read the highlighted recommendation (score ± uncertainty, slot it
   fills, survival hint, three to five computed reasons) and the shortlist. Columns: fast score and
   tier, refined marginal utility, survival probability and draft-now-vs-wait advantage (filled in
   when the refine job for the current state finishes), base value, the replacement it is measured
   against, slot, main category gains and costs, projected GP / MIN, ADP, flags. Rows in the same
   tier are effectively tied.
5. Use **Preview** on any player (the "preview" button on picker rows, the shortlist, the card, or
   the player drawer) to see your roster, open slots and category profile as if you drafted them
   (before / after / delta columns, FG% and FT% with attempts). Expand a shortlist row (▸) for the
   full nine-category breakdown: per-game stats, z-scores, strategy-weighted contributions, the
   change to your totals, and the simulated win probability per category once refinement lands.
   Use **Compare** on two or three players. Click a name for per-game details, projection source
   and eligibility provenance. The **League category profiles** tab under the board shows every
   manager's projected totals, rates with attempts, and per-category league rank after each pick.
6. Click **Draft** on the card or a row (enabled only when you are on the clock), or use the picker.
7. Change strategy at any time in the right panel: none / soft / fixed punt per category, category
   weights, risk (conservative / neutral / aggressive), simulation budget and scenario count. Every
   change is saved as an event and re-ranks immediately; punted categories stay visible.

Keyboard shortcuts: `/` focus search · `↑` `↓` move · `Enter` select, `Enter` again records ·
`Esc` back out, close dialogs and drawers. Shortcuts never fire while you type in another field.
Layout: scoreboard on top (undo lives there), picker left, best pick + Recommendations / All
players in the middle, My roster / Categories / Strategy / Teams tabs on the right, Draft history
(recent picks with "fix", the board, league profiles) at the bottom. On a phone, use the Find
player / Best picks / My team switch.

## Rookies and players returning from injury

Preseason games are not used. A rookie with no NBA season carries ESPN's projection reduced by 15 %
with games capped at 65 and a wide error bar, flagged "rookie: ESPN projection discounted". A player
with NBA history who played zero games last season is flagged "missed all of last season" and carries a
games discount: 6 % for players who were 30+ minute starters before the injury (they returned to a median
100 % of projected games since 2017), 38 % plus a 25 % rate discount for role players (who returned to 60 %). Short
seasons (a few games) need no flag: the model's games projection already reflects them. Use the risk
setting (conservative) if you want these players pushed further down.

## Punting (H2H each category)

Punting a category means conceding it every week on purpose so every pick serves the other eight.
It pays only when the players it frees up win more categories than the one you give away, which
depends on your roster, so do not plan it before the draft. After three or four picks, open
Strategy → **Punt advisor** → "Compare punt scenarios". For your current roster it completes the
rest of your draft under balanced play and under each single punt (plus the best pair), then scores
every finished roster against the league under the real rules, where the punted category still
counts. Read it as:

- **Cats won / wk**: expected categories won per weekly matchup; higher is better. Differences
  inside about two standard errors are noise; keep balanced when it ties.
- **Strong**: how many categories you'd win at least 55 % of the time. More strong categories with
  fewer toss-ups is a sturdier build in each-category scoring.
- Per-category columns: your win probability in each category under that plan; a starred column
  is the one you concede.
- **Likely next pick**: who the plan would take at your next turn, so you can see what it changes.

Apply is always an explicit click; it sets a fixed punt (weight 0 in the ranking) and re-ranks.
Re-run after each of your picks until you commit, usually by round 4 or 5; one punt is normal,
two is the practical maximum.

## In season: link the ESPN league

Once the draft is complete a **Season** tab appears.

1. In ESPN, make the league viewable to the public (League → Settings → Basic Settings). The app
   reads it without cookies and never writes to ESPN.
2. Open Season, paste the number after `leagueId=` from your ESPN URL, click **Preview mapping**.
   Each session manager is matched to an ESPN team by roster overlap (owner names only break
   ties); fix any pair with the dropdown, then **Link and sync**. CLI: `make link SESSION=<id>
   LEAGUE=<league id>`.
3. **Sync now** (or `make sync SESSION=<id>`) pulls every roster, the matchup schedule, the
   transaction log and live player status. Roster differences are recorded as one
   `roster_changed` event per sync (drops before adds, so a trade is atomic) and shown in the bar
   ("George Hu: +Ayton +Poole −Ighodaro…"). A sync that finds nothing new writes nothing.
   Auto-refresh (15 or 60 min) re-syncs while the page is open.
4. Tabs:
   - **Matchups** — this week's ESPN pairings with the projected odds for every pair; your card is
     first with per-category win chances. Odds use the real NBA games in that week; ESPN OUT and IR
     players play zero games. Use the period selector to look ahead.
   - **Power rankings** — expected categories won per week against the league, with movement since
     the previous sync. IR players never count as starters.
   - **Free agents** — unowned players ranked by what they add to *your* roster, the cheapest drop
     to make room, and the net change; live injury status and percent owned; search and position
     filters; click a name for the drawer.
   - **Results** — ESPN's actual per-category results for a week next to the projected odds.
   - **Track record** — every week's projected winner (the side that takes more than half the
     categories in most simulated weeks) with its chance, frozen when the matchup period starts, and
     ESPN's actual winner once decided: hit rate and Brier score for the season-end comparison.
     Each matchup card names the projected winner and shows both teams' per-category chances.
5. Settings differences ESPN reports (for this league: lineups lock per game, i.e. daily, while the
   session is set to weekly) are shown as warnings and never applied automatically; change the
   session in Setup if you want the simulation to use daily lineups.

### Roster moves

Under the featured matchup, **Roster moves in week N** lists every add, drop and trade ESPN
recorded during the selected matchup period, grouped by team with your team first (green arrow =
added, red arrow = dropped, a "trade" badge on both sides of a swap between managers). The same
information marks players elsewhere: the Teams panel and the Recap rosters tag players picked up
this week as "added wk N" and earlier pickups as "added", and the Performers table badges the
selected team's adds and drops ("added wk N" / "dropped wk N") next to each player's contribution,
so a player dropped mid-week still shows the games he played while rostered. Moves come from the synced transaction
log (`GET /season/moves?period=`), dated by the matchup period they landed in.

## Team performers

The page opens with a stat row (team contribution, expected, vs expected, games counted), the two
leaderboards, a diverging chart of every player's performance against expectation, a scatter of
actual against expected contribution (the dashed diagonal is "exactly as projected"), and the full
sortable table. Click a bar, point or row to select that player everywhere; a player's name opens a
drawer with actual vs expected totals, per-game lines, makes/attempts, games counted and the
per-category units that add up to the headline numbers. "How contribution and expected are
calculated" sits below the table. A week-by-week trend chart is deliberately left as an
"unavailable" note: the endpoint returns one scope at a time, so there is no per-player history to
draw; the week selector steps through weeks instead.

The **Performers** tab (after the draft, once the league is linked) ranks any team's players two ways,
per week or season to date:

- **Top contributors**: production on the league's category scale (one unit = one category standard
  deviation of per-game production; turnovers count against; FG%/FT% as impact against the pool rate),
  summed over the games ESPN actually counted for that team that week. Source: ESPN's applied box
  scores per matchup period, captured by every sync (the current week and the one before it) and kept,
  so earlier weeks can be revisited.
- **Biggest overperformers**: contribution minus the projection baseline (the snapshot's per-game
  projection x games actually played). A star can lead contribution while a bench player leads this.
  Players with no projection (prior only) or no games are shown but not ranked; fewer than three
  games is flagged "small sample".

Each row expands to the full line (points, rebounds, assists, steals, blocks, turnovers, threes,
FG and FT makes/attempts and percentages), actual next to expected, totals and per game.
Portraits come from ESPN's headshot CDN with an initials fallback.

## Corrections and undo

- **Undo last pick**: the "Undo #n" button in the scoreboard (only the most recent committed pick
  can be undone; keepers are not picks).
- **Correct an earlier pick**: "fix" next to the pick in Recent picks, or click the filled cell on
  the draft board, and choose the right player.
  Everything downstream is recomputed; the player you remove becomes available again.
- **Order fixes** (traded picks, keepers, a wrong draft order): edit them in Setup; the schedule is
  rebuilt and any already-recorded pick that no longer matches is kept and listed as a warning for
  you to review, never deleted.
- A rejected pick (duplicate player, wrong manager, not on the clock) is rolled back with the
  server's message. A revision conflict (two tabs) refreshes the state and asks you to check it.

## Imports

Setup screen, "CSV imports" (a session must be selected). Download the template for the kind you
need, fill it, paste or choose the file, **Preview** (every row shows the matched player, errors and
warnings), then **Apply** (optionally skipping rows with errors):

- **Projections**: per-game rates incl. FGM/FGA/FTM/FTA/3PM/3PA, games, minutes, optional cv and
  source. Rows without attempts are rejected because FG%/FT% impact needs volume. Applied as a
  derived snapshot the session switches to.
- **Eligibility**: primary position and `PG;SG;…` eligible positions; a source starting with
  `espn` is treated as verified, anything else is labeled unverified.
- **ADP / ranks**: platform-labeled; non-ESPN platforms are flagged.
- **Draft picks**: manager id or name plus player name; applied atomically in pick order.
- **Session JSON**: export from the recap/health screens or `make export SESSION=<id>`; import with
  the "Import session JSON" file input or `make import FILE=<file>`.

Optional read-only ESPN import of a private league (settings and completed draft) is implemented in
`backend/app/sources/espn_private.py` behind `COPILOT_ESPN_SWID` / `COPILOT_ESPN_S2` in
`backend/.env`, but it has **not** been verified against a real league from this repository and
there is no live draft feed. Treat manual entry as the supported path.

## Troubleshooting

- *Port already in use*: `make dev BACKEND_PORT=8020 FRONTEND_PORT=5180`.
- *"updating…" never finishes*: the backend is down or on another port; the top strip shows
  "offline". Picks you confirmed while offline are kept in the browser and retried with the same
  idempotency key, so they are never saved twice.
- *Refine shows "unavailable" or times out*: the fast tier A ranking is still valid; lower the
  simulation depth in the Strategy tab.
- *Simulation depth*: Strategy tab → "Simulation depth" (Quick 1.5 s, Standard 4 s default, Deep 8 s,
  Max 15 s). It is the wall-clock budget spent on the refined columns after every pick; a deeper
  setting runs more draft rollouts and fills draft-now-vs-wait for more rows. Keep it below the
  time between picks; a new pick discards an unfinished run anyway.
- *A player is missing*: search includes drafted players (greyed, with who took them). If a real
  player is absent from the snapshot, import a projection row for them or rebuild after a refresh.
- *Eligibility marked unverified*: the player had no ESPN match; import eligibility or enable
  strict mode to exclude such players.
- *Reset*: delete the session on the Setup screen (irreversible) or delete
  `data/sessions/sessions.sqlite` to remove all sessions.
