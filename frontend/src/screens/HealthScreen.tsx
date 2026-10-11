import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { HealthView } from '../api/types'
import { Badge } from '../components/common/Badge'
import { fmtDate } from '../lib/format'

export function HealthScreen() {
  const [health, setHealth] = useState<HealthView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) {
    return (
      <div className="callout error" role="alert">
        Backend unreachable: {error}
      </div>
    )
  }
  if (!health) return <p className="muted">Loading /api/health…</p>
  const demoOnly = health.snapshots.length > 0 && health.snapshots.every((s) => s.is_demo)
  return (
    <div className="stack">
      {demoOnly && (
        <div className="callout error" role="status">
          <b>Running on DEMO DATA.</b> Every snapshot is synthetic (source=demo). Players, projections and ADP are not real; use <code>make refresh</code> to build a real snapshot
          under <code>data/nba/</code>.
        </div>
      )}
      <section className="panel">
        <h2>Backend</h2>
        <div className="row">
          <Badge tone={health.status === 'ok' ? 'ok' : 'error'}>status {health.status}</Badge>
          <span>
            data dir <code>{health.data_dir}</code>
          </span>
          <span>{health.sessions} sessions</span>
          <span>
            default snapshot <code>{health.default_snapshot_id}</code>
          </span>
        </div>
        {Object.keys(health.snapshot_errors).length > 0 && (
          <div className="callout error" style={{ marginTop: 6 }}>
            Snapshot errors:
            <ul>
              {Object.entries(health.snapshot_errors).map(([k, v]) => (
                <li key={k}>
                  <code>{k}</code>: {v}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Snapshots</h2>
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th scope="col">Label</th>
                <th scope="col">Source</th>
                <th scope="col">Season</th>
                <th scope="col">Created</th>
                <th scope="col" className="num">Players</th>
                <th scope="col">ADP</th>
                <th scope="col">Rank source</th>
                <th scope="col">Health</th>
                <th scope="col">Provenance</th>
              </tr>
            </thead>
            <tbody>
              {health.snapshots.map((s) => (
                <tr key={s.snapshot_id}>
                  <td>
                    {s.label} {s.is_demo && <Badge tone="loud">DEMO</Badge>}
                    <br />
                    <span className="mono muted">{s.snapshot_id}</span>
                  </td>
                  <td>{s.source}</td>
                  <td>{s.season}</td>
                  <td className="nowrap">{fmtDate(s.created_at)}</td>
                  <td className="num">{s.n_players}</td>
                  <td>
                    {s.adp_platform ?? '—'}
                    {s.adp_asof ? <span className="muted"> ({fmtDate(s.adp_asof)})</span> : null}
                  </td>
                  <td>{s.rank_source ?? '—'}</td>
                  <td>
                    <pre style={{ margin: 0, maxHeight: 160 }}>{JSON.stringify(s.health, null, 1)}</pre>
                  </td>
                  <td>
                    <pre style={{ margin: 0, maxHeight: 160 }}>{JSON.stringify(s.provenance, null, 1)}</pre>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>data_health</h2>
        <DataHealth value={health.data_health} />
      </section>
    </div>
  )
}

function DataHealth({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value)
  if (entries.length === 0) return <p className="muted">No data_health report.</p>
  const status = typeof value.status === 'string' ? value.status : null
  return (
    <div className="stack">
      {status && <Badge tone={status === 'ok' ? 'ok' : 'warn'}>status {status}</Badge>}
      <table className="grid" aria-label="Data health">
        <thead>
          <tr>
            <th scope="col">Key</th>
            <th scope="col">Value</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k}>
              <th scope="row">{k}</th>
              <td>{typeof v === 'object' && v !== null ? <pre style={{ margin: 0 }}>{JSON.stringify(v, null, 1)}</pre> : String(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
