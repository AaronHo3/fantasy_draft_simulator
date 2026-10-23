import type { CategoryDef, FreeAgentView } from '../../api/types'
import { categoryLabel, fmtNum, fmtPct, fmtSigned, positionsText } from '../../lib/format'
import { Badge } from '../common/Badge'
import { Icon } from '../ui/Icon'
import { TeamMark } from '../ui/PlayerIdentity'

interface FreeAgentsTableProps {
  items: FreeAgentView[]
  categories: CategoryDef[]
  selectedId?: string | null
  /** Row click: select for the swap panel. */
  onSelect: (playerId: string) => void
  /** Name click: open the player drawer. Defaults to onSelect. */
  onOpen?: (playerId: string) => void
}

/** Unowned players ranked by what they add to the user's roster, each with the cheapest drop to make room. */
export function FreeAgentsTable({ items, categories, selectedId = null, onSelect, onOpen }: FreeAgentsTableProps) {
  const open = onOpen ?? onSelect
  return (
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
              <th key={c.key} scope="col" className="num" title={c.kind === 'ratio' ? `${c.numerator} ÷ ${c.denominator}` : c.higher_is_better ? undefined : 'lower is better'}>
                {categoryLabel(c.key, categories)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((f) => (
            <tr
              key={f.player.player_id}
              className={[f.flags.includes('out') ? 'drafted' : '', selectedId === f.player.player_id ? 'selected' : ''].filter(Boolean).join(' ') || undefined}
              onClick={() => onSelect(f.player.player_id)}
              style={{ cursor: 'pointer' }}
              aria-selected={selectedId === f.player.player_id}
            >
              <th scope="row">
                <button
                  type="button"
                  className="player-link"
                  onClick={(e) => {
                    e.stopPropagation()
                    onSelect(f.player.player_id)
                  }}
                >
                  {f.player.name}
                </button>{' '}
                <button
                  type="button"
                  className="small ghost icon-btn"
                  aria-label={`Details for ${f.player.name}`}
                  title="Player details"
                  onClick={(e) => {
                    e.stopPropagation()
                    open(f.player.player_id)
                  }}
                >
                  <Icon name="eye" size={13} />
                </button>
              </th>
              <td className="muted">
                <TeamMark team={f.player.team} /> · {positionsText(f.player.eligible_positions)}
              </td>
              <td>
                {f.flags.includes('out') ? <Badge tone="error">OUT</Badge> : f.flags.includes('day-to-day') ? <Badge tone="warn">DTD</Badge> : <span className="muted">{f.injury_status ?? '—'}</span>}
              </td>
              <td className="num muted">{f.percent_owned === null || f.percent_owned === undefined ? '—' : fmtPct(f.percent_owned / 100)}</td>
              <td className="num">
                <b>{fmtNum(f.score, 2)}</b>
              </td>
              <td>{f.best_drop ? f.best_drop.name : <span className="muted">—</span>}</td>
              <td className={`num ${f.swap_delta > 0 ? 'pos' : f.swap_delta < 0 ? 'neg' : ''}`}>{fmtSigned(f.swap_delta, 2)}</td>
              {categories.map((c) => (
                <td key={c.key} className={`num ${(f.z[c.key] ?? 0) > 0.5 ? 'pos' : (f.z[c.key] ?? 0) < -0.5 ? 'neg' : ''}`}>
                  {fmtSigned(f.z[c.key] ?? null, 1)}
                </td>
              ))}
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={7 + categories.length} className="muted">
                No free agents match.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
