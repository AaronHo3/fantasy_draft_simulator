# UI notes

Living note for the draft interface: design decisions, layout, and what has been done. Update when
the UI changes materially. Visual checks are done with Playwright screenshots (`.playwright-mcp/`,
ignored by git) at 1200–1440 px and 390 px.

## Design system (frontend/src/styles/index.css)

- Tokens: neutral surfaces (`--bg #eef0ee`, `--surface #fff`), ink scale (`--ink`, `--ink-2`,
  `--ink-3`), one action accent (`--accent #0e6b63`, court teal) with `--accent-soft`, status
  colors (ok / warn / error, each with a soft fill), `--mine` amber for the user's own rows,
  `--focus` orange ring. Dark "scoreboard" tokens (`--board-*`) are used only by the status strip.
- Type: system sans at 13 px; monospace for the scoreboard numerals, roster slot labels and
  pick numbers; `font-variant-numeric: tabular-nums` on every numeric cell (`.num`).
- Signature element: the dark scoreboard strip (live mode, round · pick in amber numerals, who is
  on the clock, the user's cell flips amber when it is their turn). Everything else is quiet.
- Motion: one pulsing live dot; disabled under `prefers-reduced-motion`.
- States: hover/selected/drafted rows, `aria-busy` tables with "recalculating…" badges, empty
  states (`.empty-state`), stale recommendation card (`.rec-card.stale`), focus ring everywhere.

## Layout (frontend/src/screens/DraftScreen.tsx)

```
[Scoreboard: LIVE · round/pick · on the clock · my team ▾ · next pick · undo · data · model · save]
[Find player | Best pick (hero) + tabs: Recommendations / All players | My roster / Categories / Strategy / Teams]
[Draft history (collapsible): Recent picks (fix) | Draft board (correct) | League category profiles]
```

- Picker (`PlayerPicker.tsx`): search, position chips, availability filter, inline "record pick"
  bar instead of a modal. `/` focuses search, `↑/↓` move, `Enter` selects, `Enter` again records
  for the team shown (defaults to the team on the clock; the button reads "Draft to my team"
  when that is me), `Esc` backs out. Shortcuts do not fire while typing in other inputs.
- Hero card (`RecommendationCard.tsx`): best pick for my next turn, value above replacement ± sd,
  slot filled, GP/MIN, survival hint, engine reasons, "Next best" alternatives, Draft / Preview /
  Compare. Disabled Draft explains why (someone else is on the clock, a save is pending).
- Recommendations table (`ShortlistTable.tsx`): sticky player column, Fit column (slot + top
  gains/costs), refined columns (marginal categories won, survival, draft-now), expandable
  nine-category breakdown. Row button records for whoever is on the clock.
- All players (`AllPlayersTable.tsx`): sortable projected per-game table (PTS REB AST STL BLK 3PM
  FG% FT% TO with attempts beside rates), ADP, projection source (`prior` flagged red), filters,
  preview and one-click record.
- Side tabs: My roster (slots, bench, needs, caps, legality), Categories (roster totals, z,
  punts; before/after/delta while previewing), Strategy (punts + weights; simulation settings
  in a collapsed "engine only" section), Teams (inspect any manager without losing my context).
- History drawer (`HistoryDrawer.tsx`, `RecentPicks.tsx`): recent picks with "fix" (correction
  dialog), the board, league category profiles. Undo lives in the scoreboard and asks once.
- Mobile (≤ 820 px): segmented control Find player / Best picks / My team; scoreboard wraps into
  a 2-column grid; tables scroll inside their own containers; no page-wide horizontal overflow.

## Verified (2026-10-10)

- `npm run typecheck`, `npx vitest run` (26), `npx playwright test` (3 flows: full draft loop with
  undo and reload; punt change + CSV picks import + export/import; profiles per pick, preview any
  player, breakdown rows) all pass.
- Screenshots reviewed at 1200 px (desktop) and 390 px (phone).

## Not done / ideas

- Column chooser for the recommendations table; keyboard shortcut to jump to tabs.
- Dark theme (tokens are ready, no `prefers-color-scheme` block yet).
- Virtualized all-players table (currently paged by 150 rows).
