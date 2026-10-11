import type { SnapshotMeta } from '../../api/types'
import { fmtDate } from '../../lib/format'

interface Props {
  snapshots: SnapshotMeta[]
  value: string | null
  onChange: (id: string) => void
}

export function SnapshotPicker({ snapshots, value, onChange }: Props) {
  const sel = snapshots.find((s) => s.snapshot_id === value) ?? null
  return (
    <fieldset>
      <legend>Data snapshot</legend>
      {snapshots.length === 0 ? (
        <p className="muted">No snapshots available from the backend.</p>
      ) : (
        <div className="row">
          <select aria-label="Snapshot" data-testid="setup-snapshot" value={value ?? ''} onChange={(e) => onChange(e.target.value)}>
            {snapshots.map((s) => (
              <option key={s.snapshot_id} value={s.snapshot_id}>
                {s.label} ({s.source}, {s.n_players} players)
              </option>
            ))}
          </select>
          {sel?.is_demo && (
            <span className="badge loud" data-testid="setup-demo-badge">
              DEMO DATA — synthetic players
            </span>
          )}
        </div>
      )}
      {sel && (
        <p className="muted" style={{ marginTop: 4 }}>
          source <b>{sel.source}</b> · season {sel.season} · created {fmtDate(sel.created_at)} · {sel.n_players} players · ADP {sel.adp_platform ?? '—'}
          {sel.adp_asof ? ` as of ${fmtDate(sel.adp_asof)}` : ''} · id <span className="mono">{sel.snapshot_id}</span>
        </p>
      )}
    </fieldset>
  )
}
