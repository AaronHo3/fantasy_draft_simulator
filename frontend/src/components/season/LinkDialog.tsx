import { useState } from 'react'
import { api } from '../../api/client'
import type { LinkPreview } from '../../api/types'
import { useDraftStore } from '../../store/draftStore'
import { useSeasonStore } from '../../store/seasonStore'
import { Badge } from '../common/Badge'

/** Link this session to a public ESPN league: preview the team mapping, override pairs, apply. */
export function LinkDialog({ sessionId }: { sessionId: string }) {
  const initial = new URLSearchParams(window.location.search).get('league') ?? ''
  const [leagueId, setLeagueId] = useState(initial)
  const [preview, setPreview] = useState<LinkPreview | null>(null)
  const [overrides, setOverrides] = useState<Record<string, number>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const loadSession = useDraftStore((s) => s.loadSession)
  const loadOverview = useSeasonStore((s) => s.loadOverview)
  const sync = useSeasonStore((s) => s.sync)

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const idNum = Number(leagueId)
  const valid = Number.isInteger(idNum) && idNum > 0

  const doPreview = () =>
    run(async () => {
      setPreview(await api.espnLinkPreview(sessionId, { league_id: idNum, overrides }))
    })
  const doApply = () =>
    run(async () => {
      if (!preview) return
      const mapping = Object.fromEntries(preview.mapping.map((m) => [m.manager_id, overrides[m.manager_id] ?? m.team_id]))
      await api.espnLinkApply(sessionId, { league_id: idNum, mapping })
      await loadSession(sessionId)
      await sync(sessionId)
      await loadOverview(sessionId)
    })

  return (
    <section className="panel" aria-label="Link to ESPN" data-testid="link-dialog">
      <div className="panel-head">
        <h2>Link to your ESPN league</h2>
      </div>
      <p className="muted">
        Paste the number after <span className="mono">leagueId=</span> in your ESPN URL. The league must be viewable to the public (League → Settings → Basic Settings). Read-only: nothing is ever written to ESPN.
      </p>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault()
          void doPreview()
        }}
      >
        <label htmlFor="league-id">League id</label>
        <input id="league-id" inputMode="numeric" value={leagueId} onChange={(e) => setLeagueId(e.target.value.trim())} placeholder="2075231076" data-testid="league-id" />
        <button type="submit" className="primary" disabled={!valid || busy} data-testid="link-preview">
          {busy ? 'Working…' : 'Preview mapping'}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {preview && (
        <div className="stack" style={{ marginTop: 10 }}>
          <p>
            <b>{preview.league_name}</b> · {preview.teams.length} teams on ESPN
          </p>
          <div className="table-wrap">
            <table className="grid" aria-label="Team mapping">
              <thead>
                <tr>
                  <th scope="col">Session manager</th>
                  <th scope="col">ESPN team</th>
                  <th scope="col">Owner</th>
                  <th scope="col" className="num">Roster overlap</th>
                  <th scope="col">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {preview.mapping.map((m) => (
                  <tr key={m.manager_id}>
                    <th scope="row">{m.manager_name}</th>
                    <td>
                      <select
                        aria-label={`ESPN team for ${m.manager_name}`}
                        value={overrides[m.manager_id] ?? m.team_id}
                        onChange={(e) => setOverrides((o) => ({ ...o, [m.manager_id]: Number(e.target.value) }))}
                      >
                        {preview.teams.map((t) => (
                          <option key={t.team_id} value={t.team_id}>
                            {t.name} ({t.owner_name})
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="muted">{m.owner_name}</td>
                    <td className="num">{Math.round(m.overlap * 100)}%</td>
                    <td>
                      <Badge tone={m.confidence === 'high' ? 'ok' : m.confidence === 'medium' ? 'warn' : m.confidence === 'override' ? 'accent' : 'error'}>{m.confidence}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.unmatched_managers.length > 0 && <Badge tone="error">Unmatched managers: {preview.unmatched_managers.join(', ')}</Badge>}
          {preview.settings_warnings.concat(preview.warnings).map((w) => (
            <div key={w}>
              <Badge tone="warn">{w}</Badge>
            </div>
          ))}
          <div className="row">
            <button type="button" className="primary" onClick={() => void doApply()} disabled={busy} data-testid="link-apply">
              Link and sync
            </button>
            <span className="muted">Rosters, matchups and free agents will follow ESPN from here on.</span>
          </div>
        </div>
      )}
    </section>
  )
}
