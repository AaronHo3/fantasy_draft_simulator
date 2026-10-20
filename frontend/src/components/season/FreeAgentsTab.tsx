import { useEffect, useState } from 'react'
import { PRIMITIVE_POSITIONS } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { useSeasonStore } from '../../store/seasonStore'
import { FreeAgentsTable } from './FreeAgentsTable'

export function FreeAgentsTab({ sessionId }: { sessionId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const freeAgents = useSeasonStore((s) => s.freeAgents)
  const faStatus = useSeasonStore((s) => s.faStatus)
  const faError = useSeasonStore((s) => s.faError)
  const loadFreeAgents = useSeasonStore((s) => s.loadFreeAgents)
  const openDrawer = useDraftStore((s) => s.openDrawer)
  const [q, setQ] = useState('')
  const [position, setPosition] = useState('')
  useEffect(() => {
    const t = setTimeout(() => void loadFreeAgents(sessionId, { limit: 60, q: q || null, position: position || null }), 150)
    return () => clearTimeout(t)
  }, [sessionId, q, position, loadFreeAgents])
  return (
    <div className="stack">
      <div className="row">
        <input aria-label="Search free agents" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Position" value={position} onChange={(e) => setPosition(e.target.value)}>
          <option value="">Any position</option>
          {PRIMITIVE_POSITIONS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <span className="muted">{faStatus === 'loading' ? 'Loading…' : freeAgents ? `${freeAgents.items.length} shown` : ''}</span>
      </div>
      {faError && <p className="error">{faError}</p>}
      {freeAgents && overview && <FreeAgentsTable items={freeAgents.items} categories={overview.league_categories} onSelect={(id) => openDrawer(id)} />}
      <p className="muted" style={{ fontSize: 11 }}>
        Value is the fast-ranking score against your current roster; "best drop" is the roster player whose loss costs you least; net Δ is the swap's change in weighted z.
      </p>
    </div>
  )
}
