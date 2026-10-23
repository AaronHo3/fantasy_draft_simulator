import { useState } from 'react'
import type { PerformerRow } from '../../api/types'
import { fmtNum, fmtSigned, positionsText } from '../../lib/format'
import { Badge } from '../common/Badge'
import { Portrait } from './Portrait'

export type Metric = 'contribution' | 'over_expected'
type SortKey = 'rank' | 'player' | 'games' | 'minutes' | 'contribution' | 'over_expected' | 'PTS' | 'REB' | 'AST' | 'STL' | 'BLK' | 'FG3M' | 'FG_PCT' | 'FT_PCT'

const STAT_COLS: { key: 'PTS' | 'REB' | 'AST' | 'STL' | 'BLK' | 'FG3M' | 'FG_PCT' | 'FT_PCT'; label: string }[] = [
  { key: 'PTS', label: 'PTS' },
  { key: 'REB', label: 'REB' },
  { key: 'AST', label: 'AST' },
  { key: 'STL', label: 'STL' },
  { key: 'BLK', label: 'BLK' },
  { key: 'FG3M', label: '3PM' },
  { key: 'FG_PCT', label: 'FG%' },
  { key: 'FT_PCT', label: 'FT%' },
]
const DETAIL_KEYS: { key: string; label: string }[] = [
  { key: 'PTS', label: 'Points' },
  { key: 'REB', label: 'Rebounds' },
  { key: 'AST', label: 'Assists' },
  { key: 'STL', label: 'Steals' },
  { key: 'BLK', label: 'Blocks' },
  { key: 'TOV', label: 'Turnovers (TOV)' },
  { key: 'FG3M', label: 'Threes made' },
]

const pct1 = (v: number) => `${(v * 100).toFixed(1)}%`

function cell(v: number | null | undefined, key: string): string {
  if (v === null || v === undefined) return '—'
  return key.endsWith('PCT') ? pct1(v) : fmtNum(v, Number.isInteger(v) ? 0 : 1)
}

function sortValue(r: PerformerRow, key: SortKey): number | string {
  switch (key) {
    case 'player':
      return r.player.name
    case 'rank':
    case 'games':
    case 'minutes':
    case 'contribution':
      return r[key]
    case 'over_expected':
      return r.over_expected ?? Number.NEGATIVE_INFINITY
    default:
      return r.actual[key] ?? Number.NEGATIVE_INFINITY
  }
}

interface PerformerTableProps {
  rows: PerformerRow[]
  metric: Metric
}

/** Sortable leaderboard table; each row expands to the full stat line, actual next to expected, makes and attempts. */
export function PerformerTable({ rows, metric }: PerformerTableProps) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'rank', desc: false })
  const [open, setOpen] = useState<string | null>(null)
  const sorted = [...rows].sort((a, b) => {
    // players without a baseline always sort last on "vs expected", whichever direction
    if (sort.key === 'over_expected' && (a.over_expected === null) !== (b.over_expected === null)) return a.over_expected === null ? 1 : -1
    const va = sortValue(a, sort.key)
    const vb = sortValue(b, sort.key)
    const cmp = typeof va === 'string' && typeof vb === 'string' ? va.localeCompare(vb) : Number(va) - Number(vb)
    return sort.desc ? -cmp : cmp
  })
  const toggleSort = (key: SortKey, defaultDesc: boolean) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: defaultDesc }))
  const head = (key: SortKey, label: string, title: string, defaultDesc = true, numeric = true) => (
    <th key={key} scope="col" className={numeric ? 'num' : undefined} aria-sort={sort.key === key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
      <button type="button" className="sort" onClick={() => toggleSort(key, defaultDesc)} aria-label={`Sort by ${title}`} title={title}>
        {label}
        {sort.key === key ? (sort.desc ? ' ▾' : ' ▴') : ''}
      </button>
    </th>
  )
  return (
    <div className="table-wrap">
      <table className="grid performers" aria-label="Team performers">
        <thead>
          <tr>
            {head('rank', '#', 'rank', false)}
            {head('player', 'Player', 'player name', false, false)}
            <th scope="col">Team · pos</th>
            {head('games', 'GP', 'games played')}
            {head('minutes', 'MIN', 'minutes')}
            {head('contribution', 'Contribution', 'contribution: category value produced, cumulative')}
            {head('over_expected', 'vs expected', 'vs expected: contribution minus projection x games played')}
            {STAT_COLS.map((c) => head(c.key, c.label, c.label))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const isOpen = open === r.player.player_id
            const lead = (metric === 'contribution' ? r.rank === 1 : r.over_expected !== null && r.rank === 1) && rows[0]?.player.player_id === r.player.player_id
            return [
              <tr key={r.player.player_id} className={lead ? 'leader' : undefined} data-testid="performer-row">
                <td className="num">{r.rank}</td>
                <th scope="row">
                  <span className="row-player">
                    <Portrait name={r.player.name} espnId={r.player.espn_id} team={r.player.team} size={32} />
                    <button type="button" className="player-link" onClick={() => setOpen(isOpen ? null : r.player.player_id)} aria-expanded={isOpen} aria-label={`Details for ${r.player.name}`}>
                      {r.player.name}
                    </button>
                    {r.flags.map((f) => (
                      <Badge key={f} tone={f === 'no games' ? 'neutral' : 'warn'}>
                        {f}
                      </Badge>
                    ))}
                  </span>
                </th>
                <td className="muted">
                  {r.player.team ?? '—'} · {positionsText(r.player.eligible_positions)}
                </td>
                <td className="num">{r.games}</td>
                <td className="num">{fmtNum(r.minutes, 0)}</td>
                <td className="num">{fmtNum(r.contribution, 1)}</td>
                <td className={`num ${r.over_expected === null ? 'muted' : r.over_expected > 0 ? 'pos' : r.over_expected < 0 ? 'neg' : ''}`} data-testid="over-expected">
                  {r.over_expected === null ? '—' : fmtSigned(r.over_expected, 1)}
                </td>
                {STAT_COLS.map((c) => (
                  <td key={c.key} className="num">
                    {cell(r.actual[c.key], c.key)}
                  </td>
                ))}
              </tr>,
              isOpen ? (
                <tr key={`${r.player.player_id}-detail`} className="detail">
                  <td colSpan={7 + STAT_COLS.length}>
                    <div className="performer-detail" data-testid="performer-detail">
                      <table className="grid compact" aria-label={`${r.player.name} full line`}>
                        <thead>
                          <tr>
                            <th scope="col">Stat</th>
                            <th scope="col" className="num">Actual total</th>
                            <th scope="col" className="num">Expected total</th>
                            <th scope="col" className="num">Δ</th>
                            <th scope="col" className="num">Actual / game</th>
                            <th scope="col" className="num">Expected / game</th>
                          </tr>
                        </thead>
                        <tbody>
                          {DETAIL_KEYS.map(({ key, label }) => {
                            const a = r.actual[key] ?? null
                            const e = r.expected?.[key] ?? null
                            return (
                              <tr key={key}>
                                <th scope="row">{label}</th>
                                <td className="num">{cell(a, key)}</td>
                                <td className="num">{cell(e, key)}</td>
                                <td className={`num ${a !== null && e !== null ? ((a - e) * (key === 'TOV' ? -1 : 1) > 0 ? 'pos' : (a - e) * (key === 'TOV' ? -1 : 1) < 0 ? 'neg' : '') : 'muted'}`}>
                                  {a !== null && e !== null ? fmtSigned(a - e, 1) : '—'}
                                </td>
                                <td className="num">{cell(r.actual_per_game[key], key)}</td>
                                <td className="num">{cell(r.expected_per_game?.[key], key)}</td>
                              </tr>
                            )
                          })}
                          {(
                            [
                              ['FG', 'FGM', 'FGA', 'FG_PCT'],
                              ['FT', 'FTM', 'FTA', 'FT_PCT'],
                              ['3P', 'FG3M', 'FG3A', null],
                            ] as const
                          ).map(([label, mk, ak, pk]) => (
                            <tr key={label}>
                              <th scope="row">{label} (makes/attempts)</th>
                              <td className="num">
                                {fmtNum(r.actual[mk] ?? 0, 0)}/{fmtNum(r.actual[ak] ?? 0, 0)}
                                {pk && r.actual[pk] !== null && r.actual[pk] !== undefined ? ` · ${pct1(r.actual[pk])}` : ''}
                              </td>
                              <td className="num">
                                {r.expected ? `${fmtNum(r.expected[mk] ?? 0, 0)}/${fmtNum(r.expected[ak] ?? 0, 0)}${pk && r.expected[pk] !== null && r.expected[pk] !== undefined ? ` · ${pct1(r.expected[pk])}` : ''}` : '—'}
                              </td>
                              <td className="num muted">{pk && r.actual[pk] !== null && r.actual[pk] !== undefined && r.expected?.[pk] !== null && r.expected?.[pk] !== undefined ? fmtSigned(((r.actual[pk] ?? 0) - (r.expected?.[pk] ?? 0)) * 100, 1) + ' pts' : '—'}</td>
                              <td className="num">{fmtNum(r.actual_per_game[mk] ?? 0, 1)}/{fmtNum(r.actual_per_game[ak] ?? 0, 1)}</td>
                              <td className="num">{r.expected_per_game ? `${fmtNum(r.expected_per_game[mk] ?? 0, 1)}/${fmtNum(r.expected_per_game[ak] ?? 0, 1)}` : '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                        Contribution {fmtNum(r.contribution, 2)} ({r.contribution_per_game === null ? '—' : fmtNum(r.contribution_per_game, 2)} per game) · expected{' '}
                        {r.expected_contribution === null ? 'no baseline' : fmtNum(r.expected_contribution, 2)} · {r.periods} week{r.periods === 1 ? '' : 's'} with games
                      </p>
                    </div>
                  </td>
                </tr>
              ) : null,
            ]
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7 + STAT_COLS.length} className="muted">
                Nothing to show.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
