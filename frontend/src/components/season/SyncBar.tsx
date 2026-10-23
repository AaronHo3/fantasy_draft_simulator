import { fmtDate } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { AUTO_REFRESH_OPTIONS, type AutoRefreshMinutes, useSeasonStore } from '../../store/seasonStore'
import { Badge } from '../common/Badge'
import { Icon } from '../ui/Icon'

/** "Linked to X · synced N min ago · Sync now · auto-refresh" plus the last sync's summary and warnings. */
export function SyncBar({ sessionId }: { sessionId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const syncStatus = useSeasonStore((s) => s.syncStatus)
  const syncError = useSeasonStore((s) => s.syncError)
  const lastSync = useSeasonStore((s) => s.lastSync)
  const autoRefreshMin = useSeasonStore((s) => s.autoRefreshMin)
  const setAutoRefresh = useSeasonStore((s) => s.setAutoRefresh)
  const sync = useSeasonStore((s) => s.sync)
  const lastSeq = useDraftStore((s) => s.state?.last_seq ?? null)
  const names = overview?.manager_names ?? {}
  const players = useDraftStore((s) => s.players)
  const name = (id: string) => players[id]?.name ?? id
  return (
    <section className="sync-bar" aria-label="ESPN sync">
      <div className="sync-main">
        <span className="sync-link">
          <Icon name="link" size={15} />
          <span>
            Linked to <b>{overview?.league_name ?? 'ESPN league'}</b>
            <span className="muted"> · synced {overview?.synced_at ? fmtDate(overview.synced_at) : 'never'}</span>
          </span>
        </span>
        <span className="sync-controls">
          <label className="muted" htmlFor="auto-refresh">
            Auto-refresh
          </label>
          <select id="auto-refresh" value={autoRefreshMin} onChange={(e) => setAutoRefresh(Number(e.target.value) as AutoRefreshMinutes)}>
            {AUTO_REFRESH_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m === 0 ? 'Off' : `${m} min`}
              </option>
            ))}
          </select>
          <button type="button" className="primary" onClick={() => void sync(sessionId, lastSeq)} disabled={syncStatus === 'syncing'} data-testid="sync-now">
            <Icon name="refresh" size={14} className={syncStatus === 'syncing' ? 'spin' : undefined} />
            {syncStatus === 'syncing' ? 'Syncing…' : 'Sync now'}
          </button>
        </span>
      </div>
      {syncError && <p className="error">{syncError}</p>}
      {(lastSync ?? overview) && (
        <p className="sync-summary muted">
          {lastSync?.summary ?? overview?.summary}
          {lastSync?.changes.map((c) => (
            <span key={c.manager_id} className="change">
              {' '}
              · {names[c.manager_id] ?? c.manager_id}: {c.added.map((id) => `+${name(id)}`).join(' ')} {c.dropped.map((id) => `−${name(id)}`).join(' ')}
            </span>
          ))}
        </p>
      )}
      {(lastSync?.warnings ?? overview?.warnings ?? []).length > 0 && (
        <div className="row" style={{ marginTop: 4 }}>
          {(lastSync?.warnings ?? overview?.warnings ?? []).map((w) => (
            <Badge key={w} tone="warn">
              {w}
            </Badge>
          ))}
        </div>
      )}
    </section>
  )
}
