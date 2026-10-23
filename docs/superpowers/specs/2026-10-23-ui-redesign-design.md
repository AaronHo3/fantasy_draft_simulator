# UI redesign: basketball analytics workspace

Date: 2026-10-23. Frontend only. Backend endpoints, statistical definitions, session handling,
revision safeguards and the ESPN link are unchanged.

## Intent

The app looks like a default admin template. It should read as a purpose-built fantasy
basketball analytics product: clear hierarchy, a real visual identity, and interactive visuals that
make draft and in-season decisions easier to understand.

## Goals / non-goals

- Goals: cohesive shell and design system; redesigned Draft, Season, Performers, Recap; setup and
  health restyled with the same system; interactive charts built from data the API already returns;
  responsive layouts; visible focus; no emoji.
- Non-goals: framework migration, large UI kits, new backend endpoints to fill charts, changes to
  any formula or label semantics.
- Anti-goals: decorative charts, fabricated history, colour as the only carrier of meaning,
  every section looking equally important.

## Tokens

Colour (light canvas, charcoal navigation):

| token | value | role |
|---|---|---|
| canvas | `#F3F1EC` | page background (warm stone) |
| surface | `#FFFFFF` | panels |
| surface-2 | `#F7F5F0` | table heads, inset areas |
| border | `#E3DFD6` / strong `#C8C2B6` | hairlines |
| ink | `#1A1D21` / `#4A5058` / `#767C85` | text levels |
| nav | `#22262B`, hover `#2C3137`, text `#D8DBDF`, muted `#8E959D` | sidebar and draft status strip |
| teal | `#0E7C72`, hover `#0B655D`, soft `#DCEFEB`, on-dark `#5CC8BA` | actions, selection, links |
| amber | `#B86E00` ink, `#F2A93B` on dark, soft `#FBEBCF`, mine `#FFF4DA` | on the clock, my picks, opportunities |
| good / bad | `#1F8A4C` / `#B8322A` with soft tints | favoured/unfavoured, over/under expectation |
| projected | `#9AA0A6` grey, dashed outlines | anything that is a projection, never solid colour |

Type: `Barlow Semi Condensed` 600/700 for page titles, key numbers and the status strip;
`IBM Plex Sans` 400/500/600 for body and tables; `IBM Plex Mono` for ids. Tabular numerals on
every number. Scale: 11 / 12 / 13 (body) / 15 / 18 / 24 / 34 px.

Shape: panels radius 8, controls 5, pills 999. Borders 1px; shadow only on floating layers
(drawer, modal, tooltip). Spacing scale 4 / 8 / 12 / 16 / 24.

## Shell

- Left sidebar 232px: brand, primary navigation with icons, then a context block (session name,
  linked league, last sync, data badge). Collapses to a 60px icon rail under 1180px; becomes a
  bottom tab bar under 760px.
- Main: `PageHeader` (title, description, context chips, actions) then page content. Page filters
  (team, week, scope, position) live in a `FilterBar` directly under the header, never in the
  sidebar.
- Selections persist in the hash query (`#/season?tab=…&week=…`, `#/performers?team=…&week=…`).

## Screens

Draft (control room): status strip (round/pick, on the clock, picks until my turn, next pick,
save state, model tier, data badge); picker left; recommendation hero (value ± sd from the API,
slot fit, top category impacts as aligned bars, availability risk); shortlist with per-row
category breakdown; side panel: roster by lineup slot, category profile as aligned bars with z,
strategy, teams; history with team-coloured snake board and correct-a-pick.

Season: header shows league, week, sync. Matchups tab: featured card with win probability as the
key number, nine category bars with exact values for both sides, actual ESPN totals (when the
results endpoint has them) labelled separately from projections; other matchups as a grid of
compact cards (click to feature). Power tab: ranked table plus team × category heatmap on
`cat_win_prob` (documented scale 0–100% chance to win the category against the league average),
movement arrows only when `movement` has a non-zero entry. Free agents: table plus a swap panel
for the selected row (add, drop, net Δ, per-category z bars). Results: actual values with win/loss
marks, projected row visibly muted and labelled. Track record: summary stat cards and table.

Performers: filters (team, scope, week); two leaderboards (contribution, over expectation);
diverging chart of over/under around zero; scatter of actual vs expected contribution with a
diagonal equality line; sortable table; player drawer with actual, expected, games counted and
per-category breakdown; explainer behind a disclosure and tooltips. Sparklines only when the
response carries more than one period for a player (it does not today, so an unavailable note).

Recap: summary cards, category profile bars, final rosters. Setup / Health: same panels, forms
and tables restyled; no behaviour change.

## Interactive visuals

Hand-written SVG components (no chart library): `BarList` (aligned horizontal bars with value
labels), `Diverging` (positive/negative around zero), `Scatter` (with equality line and hover),
`Heatmap` (documented colour scale, value in every cell), `ProbabilityPair` (two-sided category
bars). Every chart: hover/focus tooltip with exact value and unit, click-to-select synchronised
with the table on the same page, keyboard reachable, a legend naming actual vs projected, and an
explicit unavailable state when the data is missing.

"How this works" diagram: an SVG flow (projection snapshot → draft log / ESPN rosters →
standardised categories → simulation → recommendations and matchup odds) in an expandable help
section on Draft and Season.

## Statistical rules carried into the design

FG% / FT% stay makes ÷ attempts and show attempts; turnovers lower-is-better keeps its label;
missing values render as "—" never 0; actual / projected / demo are labelled and styled
differently; expected = projection per game × games actually played, unchanged; unit sizes are
explained in the explainer; uncertainty only where the API provides it (`value_sd`).

## Left to the builder

Exact chart dimensions, tooltip copy, icon choices, and the responsive breakpoints of individual
tables. Test ids used by the existing unit and e2e suites are preserved.
