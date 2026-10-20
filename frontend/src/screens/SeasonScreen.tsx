import { useEffect, useState } from 'react'
import { PlayerDrawer } from '../components/draft/PlayerDrawer'
import { FreeAgentsTab } from '../components/season/FreeAgentsTab'
import { LinkDialog } from '../components/season/LinkDialog'
import { MatchupsTab } from '../components/season/MatchupsTab'
import { PowerTab } from '../components/season/PowerTab'
import { PredictionsTab } from '../components/season/PredictionsTab'
import { ResultsTab } from '../components/season/ResultsTab'
import { SyncBar } from '../components/season/SyncBar'
import { buildUrl } from '../lib/router'
import { useDraftStore } from '../store/draftStore'
import { useSeasonStore } from '../store/seasonStore'

type Tab = 'matchups' | 'power' | 'free-agents' | 'results' | 'predictions'
const TABS: { id: Tab; label: string }[] = [
  { id: 'matchups', label: 'Matchups' },
  { id: 'power', label: 'Power rankings' },
  { id: 'free-agents', label: 'Free agents' },
  { id: 'results', label: 'Results' },
  { id: 'predictions', label: 'Track record' },
]

function tabFromHash(): Tab {
  const t = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('tab')
  return (TABS.some((x) => x.id === t) ? t : 'matchups') as Tab
}

/** In-season view: ESPN-synced rosters, this week's matchups, power rankings, free agents, results. */
export function SeasonScreen() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const overview = useSeasonStore((s) => s.overview)
  const overviewStatus = useSeasonStore((s) => s.overviewStatus)
  const overviewError = useSeasonStore((s) => s.overviewError)
  const loadOverview = useSeasonStore((s) => s.loadOverview)
  const start = useSeasonStore((s) => s.start)
  const stop = useSeasonStore((s) => s.stop)
  const [tab, setTab] = useState<Tab>(tabFromHash)

  useEffect(() => {
    if (sessionId) {
      void loadOverview(sessionId)
      start() // re-arm a remembered auto-refresh setting while the screen is open
    }
    return () => stop()
  }, [sessionId, loadOverview, start, stop])

  if (!sessionId || !state) {
    return (
      <div className="panel">
        <p>No session loaded.</p>
        <a href={buildUrl('setup', null)}>Go to setup</a>
      </div>
    )
  }
  if (!state.is_complete) {
    return (
      <div className="panel">
        <p>The season view opens once the draft is complete.</p>
        <a href={buildUrl('draft', sessionId)}>Back to the draft</a>
      </div>
    )
  }
  const linked = state.league.espn_league_id !== null && state.league.espn_league_id !== undefined
  const userId = state.league.user_manager_id
  const pick = (t: Tab) => {
    setTab(t)
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#/season?tab=${t}`)
  }
  return (
    <div className="stack" data-testid="season">
      {linked ? <SyncBar sessionId={sessionId} /> : <LinkDialog sessionId={sessionId} />}
      {overviewStatus === 'error' && <p className="error">{overviewError}</p>}
      <section className="panel">
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => pick(t.id)} data-testid={`season-tab-${t.id}`}>
              {t.label}
            </button>
          ))}
        </div>
        {!overview && overviewStatus === 'loading' && <p className="muted">Computing…</p>}
        {overview && tab === 'matchups' && (linked ? <MatchupsTab sessionId={sessionId} userId={userId} /> : <p className="muted">Link the league to see ESPN pairings.</p>)}
        {overview && tab === 'power' && <PowerTab />}
        {overview && tab === 'free-agents' && <FreeAgentsTab sessionId={sessionId} />}
        {overview && tab === 'results' && (linked ? <ResultsTab sessionId={sessionId} /> : <p className="muted">Link the league to see ESPN results.</p>)}
        {overview && tab === 'predictions' && (linked ? <PredictionsTab sessionId={sessionId} userId={userId} /> : <p className="muted">Link the league to start the track record.</p>)}
      </section>
      <PlayerDrawer />
    </div>
  )
}
