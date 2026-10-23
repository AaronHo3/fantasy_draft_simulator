# UI redesign implementation plan

Spec: `docs/superpowers/specs/2026-10-23-ui-redesign-design.md`. Frontend only; backend untouched.
Executed inline in one session; each task ends with `npx vitest run` + `npx tsc --noEmit -p tsconfig.app.json` green.

Global constraints: keep every `data-testid` the unit and e2e suites use; no new chart/UI framework
(only `lucide-react` for icons); FG%/FT% = makes ÷ attempts; TOV lower is better; missing ≠ zero;
actual / projected / demo visibly distinct; no fabricated history.

## Tasks

1. Design system: tokens, fonts, base styles, shared UI (`components/ui/*`: Icon, PageHeader,
   FilterBar, StatCard, ChartFrame, Tooltip, PlayerIdentity, TeamMark, States, Segmented,
   Disclosure, HowItWorks). Tests: Tooltip shows on hover/focus; ChartFrame unavailable state.
2. App shell: `AppShell` + `Sidebar` (nav gating, context block, rail/bottom-bar responsive),
   hash query helpers for persisted page selections (`lib/hashQuery.ts`, tested).
3. Charts (`components/charts/*`): BarList, Diverging, Scatter, Heatmap, ProbabilityPair, scale
   helpers in `lib/scale.ts` (tested).
4. Draft screen: status strip, recommendation hero, shortlist, roster by slot, category bars,
   board with team colours, picker; existing test ids preserved.
5. Season screen: header + sync, featured matchup, grid, power heatmap, free-agent swap panel,
   results, track record cards. Existing MatchupCard/MatchupsTab tests kept green.
6. Performers screen: filters, stat row, leaderboards, diverging + scatter, table, drawer,
   explainer behind disclosure. Existing PerformerTable/Explainer tests kept green.
7. Recap, Setup, Health restyle; Notices; modals/drawers.
8. Verification: vitest, tsc, oxlint, Playwright e2e, screenshots desktop + phone, docs
   (USER_GUIDE, PROGRESS, DECISIONS DEC-30), README screenshots section.

## Review focus

- Long player names and 14-team leagues in cards, boards and tables.
- Empty data (no synced weeks, bye weeks, unlinked league) renders helpful states, not blanks.
- Keyboard: every clickable chart element and card is focusable and operable.
- Phone width: no horizontal page scroll; tables scroll inside their frame.
- Projected vs actual never share a solid colour.
