import { useState } from 'react'
import type { CategoryDef, PerformerRow } from '../../api/types'
import { fmtNum, fmtSigned, positionsText } from '../../lib/format'
import { Badge } from '../common/Badge'
import { Icon } from '../ui/Icon'
import { TeamMark } from '../ui/PlayerIdentity'
import { PerformerDrawer } from './PerformerDrawer'
import { Portrait } from './Portrait'

export type Metric = 'contribution' | 'over_expected'

export interface MoveTag {
  kind: 'add' | 'drop'
  period: number
}
/** Player id -> that team's adds/drops of him, for the shown scope. */
export type MoveTags = Record<string, MoveTag[]>
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
  /** Row highlighted in sync with the charts. */
  selectedId?: string | null
  onSelect?: (id: string) => void
  /** Controlled drawer: which row's details are open. Uncontrolled when omitted. */
  openId?: string | null
  onOpenChange?: (id: string | null) => void
  /** League's scored categories, forwarded to the drawer. */
  categories?: CategoryDef[]
  /** Roster moves to badge next to the player (added wk N / dropped wk N). */
  moves?: MoveTags
}

/** Sortable table of every rostered player; the name opens a detail drawer with actual vs expected. */
export function PerformerTable({ rows, metric, selectedId = null, onSelect, openId, onOpenChange, categories, moves }: PerformerTableProps) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'rank', desc: false })
  const [localOpen, setLocalOpen] = useState<string | null>(null)
  const open = openId === undefined ? localOpen : openId
  const setOpen = (id: string | null) => {
    if (onOpenChange) onOpenChange(id)
    else setLocalOpen(id)
  }
  const sorted = [...rows].sort((a, b) => {
    // players without a baseline always sort last on "vs expected", whichever direction
    if (sort.key === 'over_expected' && (a.over_expected === null) !== (b.over_expected === null)) return a.over_expected === null ? 1 : -1
    const va = sortValue(a, sort.key)
    const vb = sortValue(b, sort.key)
    const cmp = typeof va === 'string' && typeof vb === 'string' ? va.localeCompare(vb) : Number(va) - Number(vb)
    return sort.desc ? -cmp : cmp
  })
  const toggleSort = (key: SortKey, defaultDesc: boolean) => setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: defaultDesc }))
  const head = (key: SortKey, label: string, title: string, defaultDesc = true, numeric = true) => (
    <th key={key} scope="col" className={numeric ? 'num' : undefined} aria-sort={sort.key === key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
      <button type="button" className="sort" onClick={() => toggleSort(key, defaultDesc)} aria-label={`Sort by ${title}`} title={title}>
        {label}
        {sort.key === key ? <Icon name={sort.desc ? 'chevron-down' : 'chevron-up'} size={11} /> : null}
      </button>
    </th>
  )
  const openRow = open ? rows.find((r) => r.player.player_id === open) ?? null : null
  return (
    <>
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
              const lead = (metric === 'contribution' ? r.rank === 1 : r.over_expected !== null && r.rank === 1) && rows[0]?.player.player_id === r.player.player_id
              const cls = [lead ? 'leader' : '', selectedId === r.player.player_id ? 'selected' : ''].filter(Boolean).join(' ')
              return (
                <tr key={r.player.player_id} className={cls || undefined} data-testid="performer-row" onClick={onSelect ? () => onSelect(r.player.player_id) : undefined} style={onSelect ? { cursor: 'pointer' } : undefined}>
                  <td className="num">{r.rank}</td>
                  <th scope="row">
                    <span className="row-player">
                      <Portrait name={r.player.name} espnId={r.player.espn_id} team={r.player.team} size={30} />
                      <button
                        type="button"
                        className="player-link"
                        onClick={(e) => {
                          e.stopPropagation()
                          setOpen(open === r.player.player_id ? null : r.player.player_id)
                        }}
                        aria-expanded={open === r.player.player_id}
                        aria-label={`Details for ${r.player.name}`}
                      >
                        {r.player.name}
                      </button>
                      {(moves?.[r.player.player_id] ?? []).map((t) => (
                        <Badge key={`${t.kind}-${t.period}`} tone={t.kind === 'add' ? 'ok' : 'error'} title={t.kind === 'add' ? `picked up in week ${t.period}; only games while rostered count` : `dropped in week ${t.period}; games before the drop still count for this team`}>
                          {t.kind === 'add' ? 'added' : 'dropped'} wk {t.period}
                        </Badge>
                      ))}
                      {r.flags.map((f) => (
                        <Badge key={f} tone={f === 'no games' ? 'neutral' : 'warn'}>
                          {f}
                        </Badge>
                      ))}
                    </span>
                  </th>
                  <td className="muted">
                    <TeamMark team={r.player.team} /> · {positionsText(r.player.eligible_positions)}
                  </td>
                  <td className="num">{r.games}</td>
                  <td className="num">{fmtNum(r.minutes, 0)}</td>
                  <td className="num">
                    <b>{fmtNum(r.contribution, 1)}</b>
                  </td>
                  <td className={`num ${r.over_expected === null ? 'muted' : r.over_expected > 0 ? 'pos' : r.over_expected < 0 ? 'neg' : ''}`} data-testid="over-expected">
                    {r.over_expected === null ? '—' : fmtSigned(r.over_expected, 1)}
                  </td>
                  {STAT_COLS.map((c) => (
                    <td key={c.key} className="num">
                      {cell(r.actual[c.key], c.key)}
                    </td>
                  ))}
                </tr>
              )
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
      {openRow && <PerformerDrawer row={openRow} onClose={() => setOpen(null)} categories={categories} />}
    </>
  )
}
