import { useEffect, useState } from 'react'
import type { LeagueConfig } from '../../api/types'
import { useDraftStore } from '../../store/draftStore'

/** Advanced: edit the live session's LeagueConfig as JSON and send `league_updated`. */
export function LeagueJsonEditor() {
  const league = useDraftStore((s) => s.state?.league ?? null)
  const leagueRevision = useDraftStore((s) => s.state?.league_revision ?? -1)
  const updateLeague = useDraftStore((s) => s.updateLeague)
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (league) setText(JSON.stringify(league, null, 2))
  }, [league, leagueRevision])

  if (!league) return <p className="muted">Load a session to edit its league JSON.</p>

  const apply = async () => {
    let parsed: LeagueConfig
    try {
      parsed = JSON.parse(text) as LeagueConfig
    } catch (e) {
      setError(`Invalid JSON: ${e instanceof Error ? e.message : String(e)}`)
      return
    }
    setBusy(true)
    setError(null)
    const ok = await updateLeague(parsed)
    setBusy(false)
    if (!ok) setError('The server rejected the league update; see the notice for details.')
  }

  return (
    <div className="stack">
      <p className="muted">
        Sends <code>league_updated</code> with this object. Changing slots, managers or order rebuilds the schedule; existing picks are kept and reviewed as warnings.
      </p>
      <textarea aria-label="League JSON" rows={14} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
      {error && (
        <p className="callout error" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <button type="button" className="primary" disabled={busy} onClick={() => void apply()}>
          Apply league JSON
        </button>
        <button type="button" onClick={() => setText(JSON.stringify(league, null, 2))}>
          Reset to current
        </button>
      </div>
    </div>
  )
}
