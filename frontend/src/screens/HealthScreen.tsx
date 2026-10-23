import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { HealthView } from '../api/types'
import { Badge } from '../components/common/Badge'
import { PageHeader } from '../components/ui/PageHeader'
import { StatCard, StatRow } from '../components/ui/StatCard'
import { ErrorState, LoadingState } from '../components/ui/States'
import { fmtDate } from '../lib/format'

/** Backend status, every projection snapshot with provenance, and the data-health report. */
export function HealthScreen() {
  const [health, setHealth] = useState<HealthView | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) return <ErrorState title="Backend unreachable">{error}</ErrorState>
  if (!health) return <LoadingState title="Loading /api/health" />
  const demoOnly = health.snapshots.length > 0 && health.snapshots.every((s) => s.is_demo)
  return (
    <div className="stack">
      <PageHeader title="Data health" description="Where the numbers come from: snapshots, their sources and freshness, and the backend's own health report." />
      {demoOnly && (
        <div className="callout error" role="status">
          <b>Running on demo data.</b> Every snapshot is synthetic (source=demo). Players, projections and ADP are not real; use <code>make refresh</code> to build a real snapshot under <code>data/nba/</code>.
        </div>
      )}
      <StatRow>
        <StatCard label="Backend" value={health.status} tone={health.status === 'ok' ? 'good' : 'bad'} detail={<code>{health.data_dir}</code>} />
        <StatCard label="Sessions" value={health.sessions} detail="stored locally" />
        <StatCard label="Snapshots" value={health.snapshots.length} detail={<code>{health.default_snapshot_id}</code>} />
      </StatRow>
      {Object.keys(health.snapshot_errors).length > 0 && (
        <div className="callout error">
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
      <section className="panel">
        <div className="section-title">
          <h2>Snapshots</h2>
        </div>
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
        <div className="section-title">
          <h2>Data health report</h2>
        </div>
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
      <div className="table-wrap">
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
    </div>
  )
}
