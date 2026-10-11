import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { PlayerView } from '../../api/types'
import { managerName } from '../../lib/draftState'
import { positionsText } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { Modal } from '../common/Modal'

interface Props {
  overall: number
  onClose: () => void
}

export function CorrectPickDialog({ overall, onClose }: Props) {
  const state = useDraftStore((s) => s.state)
  const sessionId = useDraftStore((s) => s.sessionId)
  const snapshotId = useDraftStore((s) => s.snapshotId)
  const players = useDraftStore((s) => s.players)
  const correctPick = useDraftStore((s) => s.correctPick)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<PlayerView[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!snapshotId || !q.trim()) {
      setResults([])
      return
    }
    let cancelled = false
    const t = setTimeout(() => {
      api
        .players(snapshotId, { q: q.trim(), limit: 15, sessionId })
        .then((r) => !cancelled && setResults(r))
        .catch(() => !cancelled && setResults([]))
    }, 150)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [q, snapshotId, sessionId])

  if (!state) return null
  const rec = state.picks.find((p) => p.overall === overall)
  if (!rec) return null

  const apply = async (playerId: string) => {
    setBusy(true)
    const ok = await correctPick(overall, playerId)
    setBusy(false)
    if (ok) onClose()
  }

  return (
    <Modal title={`Correct pick #${overall}`} onClose={onClose}>
      <p>
        Currently <b>{players[rec.player_id]?.name ?? rec.player_id}</b> for {managerName(state, rec.manager_id)}. Choose the player who was actually taken:
      </p>
      <input data-autofocus type="search" aria-label="Search replacement player" placeholder="Search name or team…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: '100%' }} />
      <ul className="picker-results" aria-label="Replacement candidates">
        {results.map((p) => {
          const drafted = p.drafted_by && p.player_id !== rec.player_id
          return (
            <li key={p.player_id} className={drafted ? 'drafted' : undefined} aria-disabled={!!drafted} onClick={() => !drafted && !busy && void apply(p.player_id)}>
              <span>
                <b>{p.name}</b> <span className="muted">{p.team ?? '—'}</span> · {positionsText(p.eligible_positions)}
              </span>
              <span className="muted">{drafted ? `drafted by ${managerName(state, p.drafted_by!)} at #${p.drafted_overall}` : p.player_id === rec.player_id ? 'current' : 'available'}</span>
            </li>
          )
        })}
        {q.trim() && results.length === 0 && <li className="muted">No players match.</li>}
      </ul>
    </Modal>
  )
}
