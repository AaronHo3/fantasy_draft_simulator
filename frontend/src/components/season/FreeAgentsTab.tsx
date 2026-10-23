import { useEffect, useState } from 'react'
import type { FreeAgentView } from '../../api/types'
import { categoryLabel, fmtNum, fmtSigned, PRIMITIVE_POSITIONS, positionsText } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { useSeasonStore } from '../../store/seasonStore'
import { Diverging } from '../charts/Diverging'
import { Badge } from '../common/Badge'
import { ChartFrame } from '../ui/ChartFrame'
import { Icon } from '../ui/Icon'
import { PlayerIdentity } from '../ui/PlayerIdentity'
import { EmptyState, ErrorState } from '../ui/States'
import { FreeAgentsTable } from './FreeAgentsTable'

/** Unowned players ranked by what they add; selecting a row explains the add/drop swap category by category. */
export function FreeAgentsTab({ sessionId }: { sessionId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const freeAgents = useSeasonStore((s) => s.freeAgents)
  const faStatus = useSeasonStore((s) => s.faStatus)
  const faError = useSeasonStore((s) => s.faError)
  const loadFreeAgents = useSeasonStore((s) => s.loadFreeAgents)
  const openDrawer = useDraftStore((s) => s.openDrawer)
  const [q, setQ] = useState('')
  const [position, setPosition] = useState('')
  const [hideOut, setHideOut] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  useEffect(() => {
    const t = setTimeout(() => void loadFreeAgents(sessionId, { limit: 60, q: q || null, position: position || null }), 150)
    return () => clearTimeout(t)
  }, [sessionId, q, position, loadFreeAgents])
  const items = freeAgents?.items ?? []
  const visible = hideOut ? items.filter((f) => !f.flags.includes('out')) : items
  const selected: FreeAgentView | null = visible.find((f) => f.player.player_id === selectedId) ?? visible[0] ?? null
  const cats = overview?.league_categories ?? []
  const filtersActive = q !== '' || position !== '' || !hideOut
  return (
    <div className="stack">
      <div className="filter-bar">
        <span className="field search-field" style={{ width: 220 }}>
          <Icon name="search" size={14} />
          <input aria-label="Search free agents" placeholder="Search name" value={q} onChange={(e) => setQ(e.target.value)} />
        </span>
        <span className="field">
          <label htmlFor="fa-pos">Position</label>
          <select id="fa-pos" aria-label="Position" value={position} onChange={(e) => setPosition(e.target.value)}>
            <option value="">Any</option>
            {PRIMITIVE_POSITIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </span>
        <label className="field">
          <input type="checkbox" checked={hideOut} onChange={(e) => setHideOut(e.target.checked)} aria-label="Hide OUT players" />
          Hide OUT players
        </label>
        {filtersActive && (
          <button
            type="button"
            className="small ghost"
            onClick={() => {
              setQ('')
              setPosition('')
              setHideOut(true)
            }}
          >
            <Icon name="close" size={12} /> Reset filters
          </button>
        )}
        <span className="status">{faStatus === 'loading' ? 'Loading…' : freeAgents ? `${visible.length} shown` : ''}</span>
      </div>
      {faError && <ErrorState title="Could not load free agents">{faError}</ErrorState>}
      {freeAgents && overview && visible.length === 0 && <EmptyState title="No free agents match">Clear the search or position filter to see the full list.</EmptyState>}
      {selected && overview && (
        <ChartFrame
          title="Proposed swap"
          description="Value is the fast-ranking score against your current roster (weighted z); the best drop is the roster player whose loss costs you least; net Δ is the swap's change in weighted z. Bars show the added player's z by category."
          testId="swap-panel"
          legend={[
            { label: 'strength', swatch: 'good' },
            { label: 'weakness', swatch: 'bad' },
          ]}
        >
          <div className="swap">
            <div className="swap-sides">
              <div className="swap-side add">
                <span className="swap-k">
                  <Icon name="arrow-up" size={13} /> Add
                </span>
                <PlayerIdentity name={selected.player.name} team={selected.player.team} positions={selected.player.eligible_positions} espnId={selected.player.espn_id} size={40} meta={selected.percent_owned != null ? `${fmtNum(selected.percent_owned, 0)}% owned` : undefined} />
                <span className="swap-val">
                  value <b>{fmtNum(selected.score, 2)}</b>
                </span>
                {selected.flags.includes('out') && <Badge tone="error">OUT</Badge>}
                {selected.flags.includes('day-to-day') && <Badge tone="warn">day-to-day</Badge>}
              </div>
              <Icon name="swap" size={20} className="swap-icon" />
              <div className="swap-side drop">
                <span className="swap-k">
                  <Icon name="arrow-down" size={13} /> Drop
                </span>
                {selected.best_drop ? (
                  <>
                    <PlayerIdentity name={selected.best_drop.name} team={selected.best_drop.team} positions={selected.best_drop.eligible_positions} espnId={selected.best_drop.espn_id} size={40} />
                    <span className="swap-val">
                      value <b>{fmtNum(selected.drop_value, 2)}</b>
                    </span>
                  </>
                ) : (
                  <span className="muted">No drop needed (open roster spot)</span>
                )}
              </div>
              <div className={`swap-net ${selected.swap_delta > 0 ? 'good' : selected.swap_delta < 0 ? 'bad' : ''}`}>
                <span className="swap-k">Net Δ</span>
                <span className="swap-big">{fmtSigned(selected.swap_delta, 2)}</span>
                <span className="muted small-text">weighted z</span>
              </div>
            </div>
            <div className="swap-cats">
              <Diverging
                rows={cats.map((c) => ({ id: c.key, label: categoryLabel(c.key, cats), value: selected.z[c.key] ?? null, sublabel: c.higher_is_better ? undefined : 'lower is better' }))}
                format={(v) => v.toFixed(1)}
                unit="z (season value vs league pool)"
                negativeLabel="below pool"
                positiveLabel="above pool"
              />
            </div>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button type="button" className="small" onClick={() => openDrawer(selected.player.player_id)}>
              <Icon name="eye" size={13} /> Player details
            </button>
            <span className="muted small-text">
              {selected.player.team ?? 'FA'} · {positionsText(selected.player.eligible_positions)} · {selected.injury_status ?? 'status unknown'}
            </span>
          </div>
        </ChartFrame>
      )}
      {freeAgents && overview && visible.length > 0 && (
        <FreeAgentsTable items={visible} categories={overview.league_categories} selectedId={selected?.player.player_id ?? null} onSelect={(id) => setSelectedId(id)} onOpen={(id) => openDrawer(id)} />
      )}
    </div>
  )
}
