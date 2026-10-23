import { useEffect, useState } from 'react'
import { PlayerDrawer } from '../components/draft/PlayerDrawer'
import { FreeAgentsTab } from '../components/season/FreeAgentsTab'
import { LinkDialog } from '../components/season/LinkDialog'
import { MatchupsTab } from '../components/season/MatchupsTab'
import { PowerTab } from '../components/season/PowerTab'
import { PredictionsTab } from '../components/season/PredictionsTab'
import { ResultsTab } from '../components/season/ResultsTab'
import { SyncBar } from '../components/season/SyncBar'
import { HowItWorks } from '../components/ui/HowItWorks'
import { PageHeader, type ContextChip } from '../components/ui/PageHeader'
import { Segmented } from '../components/ui/Segmented'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { fmtDate } from '../lib/format'
import { readHashQuery, replaceHashQuery } from '../lib/hashQuery'
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
  const t = readHashQuery(window.location.hash).tab
  return (TABS.some((x) => x.id === t) ? t : 'matchups') as Tab
}

/** In-season view: ESPN-synced rosters, this week's matchups, power rankings, free agents, results. */
export function SeasonScreen() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const isDemo = useDraftStore((s) => s.snapshot?.is_demo ?? false)
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
      <EmptyState title="No session loaded" action={<a href={buildUrl('setup', null)}>Go to setup</a>}>
        The season view follows a drafted session that is linked to an ESPN league.
      </EmptyState>
    )
  }
  if (!state.is_complete) {
    return (
      <EmptyState title="The season view opens once the draft is complete" action={<a href={buildUrl('draft', sessionId)}>Back to the draft</a>}>
        Record every pick first; rosters, matchups and free agents then follow ESPN.
      </EmptyState>
    )
  }
  const linked = state.league.espn_league_id !== null && state.league.espn_league_id !== undefined
  const userId = state.league.user_manager_id
  const pick = (t: Tab) => {
    setTab(t)
    replaceHashQuery({ tab: t })
  }
  const chips: ContextChip[] = []
  if (overview?.league_name) chips.push({ label: 'League', value: overview.league_name, tone: 'accent' })
  if (overview) chips.push({ label: 'Week', value: overview.current_period })
  if (overview?.synced_at) chips.push({ label: 'Synced', value: fmtDate(overview.synced_at).slice(5, 16), title: fmtDate(overview.synced_at) })
  if (isDemo) chips.push({ label: 'Data', value: 'demo', tone: 'demo', title: 'Synthetic players and projections' })

  return (
    <div className="stack season-screen" data-testid="season">
      <PageHeader
        title="Season"
        description="This week's matchup odds, power rankings, free-agent swaps and ESPN results for your league. Odds come from simulated weeks on real NBA schedules; results come from ESPN."
        chips={chips}
      />
      {linked ? <SyncBar sessionId={sessionId} /> : <LinkDialog sessionId={sessionId} />}
      {overviewStatus === 'error' && <ErrorState title="Could not load the season overview">{overviewError}</ErrorState>}
      <section className="panel">
        <Segmented<Tab> label="Season views" value={tab} onChange={pick} options={TABS.map((t) => ({ id: t.id, label: t.label, testId: `season-tab-${t.id}` }))} />
        {!overview && overviewStatus === 'loading' && <LoadingState title="Simulating this week's matchups" />}
        {overview && tab === 'matchups' && (linked ? <MatchupsTab sessionId={sessionId} userId={userId} /> : <EmptyState title="Link the league to see ESPN pairings" />)}
        {overview && tab === 'power' && <PowerTab />}
        {overview && tab === 'free-agents' && <FreeAgentsTab sessionId={sessionId} />}
        {overview && tab === 'results' && (linked ? <ResultsTab sessionId={sessionId} /> : <EmptyState title="Link the league to see ESPN results" />)}
        {overview && tab === 'predictions' && (linked ? <PredictionsTab sessionId={sessionId} userId={userId} /> : <EmptyState title="Link the league to start the track record" />)}
      </section>
      <HowItWorks />
      <PlayerDrawer />
    </div>
  )
}
