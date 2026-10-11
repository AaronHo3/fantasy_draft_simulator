import { api } from '../api/client'
import { ProfileTable } from '../components/draft/CategoryProfileTable'
import { OpponentRosters } from '../components/draft/OpponentRosters'
import { PlayerDrawer } from '../components/draft/PlayerDrawer'
import { buildUrl } from '../lib/router'
import { selectRecCurrent, useDraftStore } from '../store/draftStore'

export function RecapScreen() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const rec = useDraftStore((s) => s.rec)
  const current = useDraftStore(selectRecCurrent)
  const notify = useDraftStore((s) => s.notify)
  if (!sessionId || !state) {
    return (
      <div className="panel">
        <p>No session loaded.</p>
        <a href={buildUrl('setup', null)}>Go to setup</a>
      </div>
    )
  }

  const exportJson = async () => {
    try {
      const data = await api.exportSession(sessionId)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `draft-session-${sessionId}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      notify('error', `Export failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  return (
    <div className="stack" data-testid="recap">
      <section className="panel">
        <div className="panel-head">
          <h2>{state.is_complete ? 'Draft complete' : 'Draft recap (in progress)'}</h2>
          <div className="row">
            <button type="button" className="primary" onClick={() => void exportJson()}>
              Export session JSON
            </button>
            {!state.is_complete && <a href={buildUrl('draft', sessionId)}>Back to the draft</a>}
          </div>
        </div>
        <p className="muted">
          {state.picks.length} of {state.schedule.length} picks recorded · format {state.league.scoring_format} ({state.format_confirmed ? 'confirmed' : 'not confirmed'})
        </p>
      </section>
      <section className="panel">
        <h3>My category profile</h3>
        {current && rec ? <ProfileTable profile={rec.category_profile} categories={state.league.categories ?? []} /> : <p className="muted">updating…</p>}
      </section>
      <section className="panel">
        <h3>Final rosters</h3>
        <OpponentRosters />
      </section>
      <PlayerDrawer />
    </div>
  )
}
