import { useMemo, useState } from 'react'
import type { PlayerView } from '../../api/types'
import { managerName, pickLookup, userIsOnClock } from '../../lib/draftState'
import { fmtNum, fmtRate, PRIMITIVE_POSITIONS, positionsText } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { PlayerName } from '../common/PlayerName'

type SortKey = 'rank' | 'adp' | 'name' | 'team' | 'GP' | 'MIN' | 'PTS' | 'REB' | 'AST' | 'STL' | 'BLK' | 'FG3M' | 'FG_PCT' | 'FT_PCT' | 'TOV'
type Availability = 'available' | 'drafted' | 'all'
const STAT_COLS: { key: SortKey; label: string; title: string }[] = [
  { key: 'GP', label: 'GP', title: 'projected games played' },
  { key: 'MIN', label: 'MIN', title: 'projected minutes per game' },
  { key: 'PTS', label: 'PTS', title: 'points per game' },
  { key: 'REB', label: 'REB', title: 'rebounds per game' },
  { key: 'AST', label: 'AST', title: 'assists per game' },
  { key: 'STL', label: 'STL', title: 'steals per game' },
  { key: 'BLK', label: 'BLK', title: 'blocks per game' },
  { key: 'FG3M', label: '3PM', title: 'threes made per game' },
  { key: 'FG_PCT', label: 'FG%', title: 'FGM ÷ FGA (attempts shown)' },
  { key: 'FT_PCT', label: 'FT%', title: 'FTM ÷ FTA (attempts shown)' },
  { key: 'TOV', label: 'TO', title: 'turnovers per game (lower is better)' },
]

function statValue(p: PlayerView, k: SortKey): number | null {
  switch (k) {
    case 'rank':
      return p.rank
    case 'adp':
      return p.adp
    case 'name':
    case 'team':
      return null
    case 'FG_PCT':
      return p.per_game.FGA ? p.per_game.FGM / p.per_game.FGA : null
    case 'FT_PCT':
      return p.per_game.FTA ? p.per_game.FTM / p.per_game.FTA : null
    default:
      return p.per_game[k] ?? null
  }
}

/** Every player in the snapshot with projected per-game stats; sortable, filterable, with one-click record. */
export function AllPlayersTable() {
  const state = useDraftStore((s) => s.state)
  const players = useDraftStore((s) => s.players)
  const playersStatus = useDraftStore((s) => s.playersStatus)
  const snapshot = useDraftStore((s) => s.snapshot)
  const pendingCommit = useDraftStore((s) => s.pendingCommit)
  const commitPick = useDraftStore((s) => s.commitPick)
  const previewPlayerId = useDraftStore((s) => s.previewPlayerId)
  const setPreview = useDraftStore((s) => s.setPreview)
  const [q, setQ] = useState('')
  const [positions, setPositions] = useState<Set<string>>(() => new Set())
  const [availability, setAvailability] = useState<Availability>('available')
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'rank', dir: 1 })
  const [limit, setLimit] = useState(150)
  const picks = useMemo(() => (state ? pickLookup(state) : new Map()), [state])

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const list = Object.values(players).filter((p) => {
      const drafted = picks.has(p.player_id)
      if (availability === 'available' && drafted) return false
      if (availability === 'drafted' && !drafted) return false
      if (positions.size > 0 && !p.eligible_positions.some((x) => positions.has(x))) return false
      if (needle && !p.name.toLowerCase().includes(needle) && !(p.team ?? '').toLowerCase().includes(needle)) return false
      return true
    })
    const dir = sort.dir
    list.sort((a, b) => {
      if (sort.key === 'name') return dir * a.name.localeCompare(b.name)
      if (sort.key === 'team') return dir * (a.team ?? 'zz').localeCompare(b.team ?? 'zz')
      const va = statValue(a, sort.key)
      const vb = statValue(b, sort.key)
      if (va === null && vb === null) return 0
      if (va === null) return 1
      if (vb === null) return -1
      return dir * (va - vb)
    })
    return list
  }, [players, picks, availability, positions, q, sort])

  if (!state) return null
  const onClock = state.on_clock_manager_id
  const uid = state.league.user_manager_id
  const meOnClock = userIsOnClock(state)
  const setSortKey = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'rank' || key === 'adp' || key === 'name' || key === 'team' || key === 'TOV' ? 1 : -1 }))
  const arrow = (key: SortKey) => (sort.key === key ? <span className="dir">{sort.dir === 1 ? '▲' : '▼'}</span> : null)
  const togglePos = (p: string) =>
    setPositions((prev) => {
      const next = new Set(prev)
      if (next.has(p)) next.delete(p)
      else next.add(p)
      return next
    })

  return (
    <div>
      <div className="picker-filters">
        <input type="search" aria-label="Filter players by name or team" placeholder="Filter name or team…" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 180 }} />
        <div className="chips" role="group" aria-label="Position filter">
          {PRIMITIVE_POSITIONS.map((p) => (
            <button type="button" key={p} aria-pressed={positions.has(p)} onClick={() => togglePos(p)}>
              {p}
            </button>
          ))}
        </div>
        <select aria-label="Availability" value={availability} onChange={(e) => setAvailability(e.target.value as Availability)}>
          <option value="available">available</option>
          <option value="drafted">drafted</option>
          <option value="all">everyone</option>
        </select>
        <span className="muted small-text">
          {rows.length} players · projected per game{snapshot ? ` · ${snapshot.is_demo ? 'DEMO data' : snapshot.label}` : ''}
        </span>
      </div>
      {playersStatus === 'loading' && <p className="muted">Loading player index…</p>}
      {playersStatus === 'error' && <p className="callout error">The player index could not be loaded. Search still works in the picker.</p>}
      <div className="table-wrap tall">
        <table className="grid" data-testid="all-players">
          <thead>
            <tr>
              <th scope="col" className="num sortable" onClick={() => setSortKey('rank')}>
                Rk{arrow('rank')}
              </th>
              <th scope="col" className="sticky-col sortable" onClick={() => setSortKey('name')}>
                Player{arrow('name')}
              </th>
              <th scope="col" className="sortable" onClick={() => setSortKey('team')}>
                Team{arrow('team')}
              </th>
              <th scope="col">Pos</th>
              {STAT_COLS.map((c) => (
                <th scope="col" key={c.key} className="num sortable" title={c.title} onClick={() => setSortKey(c.key)}>
                  {c.label}
                  {arrow(c.key)}
                </th>
              ))}
              <th scope="col" className="num sortable" onClick={() => setSortKey('adp')}>
                ADP{arrow('adp')}
              </th>
              <th scope="col">Source</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((p) => {
              const rec = picks.get(p.player_id)
              const drafted = rec !== undefined
              return (
                <tr key={p.player_id} className={drafted ? 'drafted' : previewPlayerId === p.player_id ? 'selected' : undefined} data-testid="all-row" data-player-id={p.player_id}>
                  <td className="num">{fmtNum(p.rank, 0)}</td>
                  <th scope="row" className="sticky-col">
                    <PlayerName playerId={p.player_id} name={p.name} />
                    {drafted && rec && (
                      <span className="muted small-text">
                        {' '}
                        · {managerName(state, rec.manager_id)} #{rec.overall}
                      </span>
                    )}
                  </th>
                  <td>{p.team ?? '—'}</td>
                  <td>{positionsText(p.eligible_positions)}</td>
                  {STAT_COLS.map((c) => {
                    const v = statValue(p, c.key)
                    if (c.key === 'FG_PCT' || c.key === 'FT_PCT') {
                      const att = c.key === 'FG_PCT' ? p.per_game.FGA : p.per_game.FTA
                      return (
                        <td className="num" key={c.key}>
                          {fmtRate(v)} <span className="muted">{fmtNum(att, 1)}</span>
                        </td>
                      )
                    }
                    return (
                      <td className="num" key={c.key}>
                        {fmtNum(v, c.key === 'GP' ? 0 : 1)}
                      </td>
                    )
                  })}
                  <td className="num">{fmtNum(p.adp, 1)}</td>
                  <td className={p.projection_source === 'prior' ? 'neg' : 'muted'} title={p.projection_source === 'prior' ? 'no history and no ESPN projection: rank-tier prior only' : undefined}>
                    {p.projection_source}
                  </td>
                  <td className="actions">
                    {!drafted && (
                      <>
                        <button type="button" className="small ghost" aria-pressed={previewPlayerId === p.player_id} onClick={() => setPreview(previewPlayerId === p.player_id ? null : p.player_id)}>
                          preview
                        </button>{' '}
                        {onClock && (
                          <button
                            type="button"
                            className={meOnClock ? 'small primary' : 'small'}
                            disabled={pendingCommit !== null}
                            onClick={() => void commitPick(p.player_id, onClock)}
                            title={meOnClock ? `Draft ${p.name} to my team` : `Record ${p.name} for ${managerName(state, onClock)}`}
                          >
                            {meOnClock ? 'Draft' : `Record for ${managerName(state, onClock)}`}
                          </button>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              )
            })}
            {rows.length === 0 && playersStatus === 'ready' && (
              <tr>
                <td colSpan={18}>
                  <div className="empty-state">No players match these filters.</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {rows.length > limit && (
        <button type="button" className="small" style={{ marginTop: 6 }} onClick={() => setLimit((l) => l + 150)}>
          Show {Math.min(150, rows.length - limit)} more ({rows.length - limit} hidden)
        </button>
      )}
      <p className="muted small-text" style={{ marginTop: 4 }}>
        {uid && !meOnClock && onClock ? `${managerName(state, onClock)} is on the clock: the row button records the pick for them.` : 'You are on the clock: the row button drafts to your team.'} Percentages show attempts per game beside the rate.
      </p>
    </div>
  )
}
