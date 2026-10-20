import { useState } from 'react'
import type { CategoryDef, FreeAgentView } from '../../api/types'
import { categoryLabel, fmtNum, fmtPct, fmtSigned, positionsText } from '../../lib/format'
import { Badge } from '../common/Badge'

interface FreeAgentsTableProps {
  items: FreeAgentView[]
  categories: CategoryDef[]
  onSelect: (playerId: string) => void
}

/** Unowned players ranked by what they add to the user's roster, each with the cheapest drop to make room. */
export function FreeAgentsTable({ items, categories, onSelect }: FreeAgentsTableProps) {
  const [hideOut, setHideOut] = useState(false)
  const rows = hideOut ? items.filter((f) => !f.flags.includes('out')) : items
  return (
    <div className="stack">
      <label className="row" style={{ gap: 6 }}>
        <input type="checkbox" checked={hideOut} onChange={(e) => setHideOut(e.target.checked)} aria-label="Hide OUT players" />
        Hide OUT players
      </label>
      <div className="table-wrap tall">
        <table className="grid" aria-label="Free agents">
          <thead>
            <tr>
              <th scope="col">Player</th>
              <th scope="col">Team · pos</th>
              <th scope="col">Status</th>
              <th scope="col" className="num">% owned</th>
              <th scope="col" className="num">Value</th>
              <th scope="col">Best drop</th>
              <th scope="col" className="num">Net Δ</th>
              {categories.map((c) => (
                <th key={c.key} scope="col" className="num">
                  {categoryLabel(c.key, categories)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.player.player_id} className={f.flags.includes('out') ? 'drafted' : undefined} onClick={() => onSelect(f.player.player_id)} style={{ cursor: 'pointer' }}>
                <th scope="row">
                  <button type="button" className="player-link" onClick={(e) => { e.stopPropagation(); onSelect(f.player.player_id) }}>
                    {f.player.name}
                  </button>
                </th>
                <td className="muted">
                  {f.player.team ?? '—'} · {positionsText(f.player.eligible_positions)}
                </td>
                <td>
                  {f.flags.includes('out') ? <Badge tone="error">OUT</Badge> : f.flags.includes('day-to-day') ? <Badge tone="warn">DTD</Badge> : <span className="muted">{f.injury_status ?? '—'}</span>}
                </td>
                <td className="num muted">{f.percent_owned === null || f.percent_owned === undefined ? '—' : fmtPct(f.percent_owned / 100)}</td>
                <td className="num">{fmtNum(f.score, 2)}</td>
                <td>{f.best_drop ? f.best_drop.name : <span className="muted">—</span>}</td>
                <td className={`num ${f.swap_delta > 0 ? 'pos' : f.swap_delta < 0 ? 'neg' : ''}`}>{fmtSigned(f.swap_delta, 2)}</td>
                {categories.map((c) => (
                  <td key={c.key} className={`num ${(f.z[c.key] ?? 0) > 0.5 ? 'pos' : (f.z[c.key] ?? 0) < -0.5 ? 'neg' : ''}`}>
                    {fmtSigned(f.z[c.key] ?? 0, 1)}
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7 + categories.length} className="muted">
                  No free agents match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
