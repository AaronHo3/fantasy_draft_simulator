import { useState } from 'react'
import { AllPlayersTable } from '../components/draft/AllPlayersTable'
import { CategoryProfileTable } from '../components/draft/CategoryProfileTable'
import { CompareView } from '../components/draft/CompareView'
import { HistoryDrawer } from '../components/draft/HistoryDrawer'
import { PlayerDrawer } from '../components/draft/PlayerDrawer'
import { PlayerPicker } from '../components/draft/PlayerPicker'
import { RecommendationCard } from '../components/draft/RecommendationCard'
import { RosterPanel } from '../components/draft/RosterPanel'
import { Scoreboard } from '../components/draft/Scoreboard'
import { ShortlistTable } from '../components/draft/ShortlistTable'
import { StrategyPanel } from '../components/draft/StrategyPanel'
import { TeamsPanel } from '../components/draft/TeamsPanel'
import { HowItWorks } from '../components/ui/HowItWorks'
import { Segmented } from '../components/ui/Segmented'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { buildUrl } from '../lib/router'
import { selectRecCurrent, useDraftStore } from '../store/draftStore'

const NO_WARNINGS: string[] = []
type WorkTab = 'recommendations' | 'players'
type SideTab = 'roster' | 'categories' | 'strategy' | 'teams'
type MobilePane = 'find' | 'picks' | 'mine'

/** Draft night control room: status strip, picker, recommendation hero and shortlist, my team. */
export function DraftScreen() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const stateStatus = useDraftStore((s) => s.stateStatus)
  const stateError = useDraftStore((s) => s.stateError)
  const formatConfirmed = useDraftStore((s) => s.state?.format_confirmed ?? true)
  const scoringFormat = useDraftStore((s) => s.state?.league.scoring_format ?? '')
  const warnings = useDraftStore((s) => s.state?.warnings ?? NO_WARNINGS)
  const hasState = useDraftStore((s) => s.state !== null)
  const isComplete = useDraftStore((s) => s.state?.is_complete ?? false)
  const shortlistCount = useDraftStore((s) => (selectRecCurrent(s) && s.rec ? s.rec.shortlist.length : null))
  const playersStatus = useDraftStore((s) => s.playersStatus)
  const confirmFormat = useDraftStore((s) => s.confirmFormat)
  const refreshState = useDraftStore((s) => s.refreshState)
  const activePunts = useDraftStore((s) => Object.keys(s.state?.strategy.punts ?? {}).length)
  const [workTab, setWorkTab] = useState<WorkTab>('recommendations')
  const [sideTab, setSideTab] = useState<SideTab>('roster')
  const [pane, setPane] = useState<MobilePane>('picks')

  if (!sessionId) {
    return (
      <EmptyState title="No draft open" action={<a href={buildUrl('setup', null)}>Create a league or resume a saved draft</a>}>
        Picks are recorded against a session; start one in Setup.
      </EmptyState>
    )
  }
  if (stateStatus === 'error') {
    return (
      <ErrorState
        title={`Could not load draft ${sessionId}`}
        action={
          <>
            <button type="button" onClick={() => void refreshState()}>
              Try again
            </button>
            <a href={buildUrl('setup', null)}>Back to setup</a>
          </>
        }
      >
        {stateError}
      </ErrorState>
    )
  }
  if (!hasState) return <LoadingState title="Loading draft" />

  return (
    <>
      <Scoreboard />
      {(!formatConfirmed || warnings.length > 0 || isComplete) && (
        <div className="draft-notices">
          {!formatConfirmed && (
            <div className="callout warn" role="alert" data-testid="format-warning">
              Scoring format not confirmed: rankings assume <b>{scoringFormat}</b>.{' '}
              <button type="button" className="small" onClick={() => void confirmFormat()}>
                Confirm format
              </button>{' '}
              or change it in <a href={buildUrl('setup', sessionId)}>Setup</a>.
            </div>
          )}
          {warnings.length > 0 && (
            <div className="callout warn" role="status">
              {warnings.map((w) => (
                <div key={w}>{w}</div>
              ))}
            </div>
          )}
          {isComplete && (
            <div className="callout ok" role="status">
              Every pick is recorded. <a href={buildUrl('recap', sessionId)}>Open the recap</a> for final rosters and your category profile.
            </div>
          )}
        </div>
      )}
      <div className="mobile-tabs" role="tablist" aria-label="Sections">
        <button type="button" role="tab" aria-selected={pane === 'find'} onClick={() => setPane('find')}>
          Find player
        </button>
        <button type="button" role="tab" aria-selected={pane === 'picks'} onClick={() => setPane('picks')}>
          Best picks
        </button>
        <button type="button" role="tab" aria-selected={pane === 'mine'} onClick={() => setPane('mine')}>
          My team
        </button>
      </div>
      <div className="draft-grid">
        <aside className="col-picker" data-mobile-hidden={pane !== 'find'}>
          <PlayerPicker />
        </aside>
        <div className="col-work" data-mobile-hidden={pane !== 'picks'}>
          <RecommendationCard />
          <section className="panel" aria-label="Player workspace">
            <Segmented<WorkTab>
              label="Workspace"
              value={workTab}
              onChange={setWorkTab}
              options={[
                { id: 'recommendations', label: 'Recommendations', count: shortlistCount ?? undefined, testId: 'tab-recommendations' },
                { id: 'players', label: 'All players', count: playersStatus === 'loading' ? 'loading…' : undefined, testId: 'tab-players' },
              ]}
            />
            {workTab === 'recommendations' ? <ShortlistTable /> : <AllPlayersTable />}
          </section>
        </div>
        <aside className="col-side" data-mobile-hidden={pane !== 'mine'}>
          <section className="panel" aria-label="My team and strategy">
            <Segmented<SideTab>
              label="My team"
              value={sideTab}
              onChange={setSideTab}
              options={[
                { id: 'roster', label: 'Roster', testId: 'tab-roster' },
                { id: 'categories', label: 'Categories', testId: 'tab-categories' },
                { id: 'strategy', label: 'Strategy', count: activePunts > 0 ? `${activePunts} punt${activePunts > 1 ? 's' : ''}` : undefined, testId: 'tab-strategy' },
                { id: 'teams', label: 'Teams', testId: 'tab-teams' },
              ]}
            />
            {sideTab === 'roster' && <RosterPanel />}
            {sideTab === 'categories' && <CategoryProfileTable />}
            {sideTab === 'strategy' && <StrategyPanel />}
            {sideTab === 'teams' && <TeamsPanel />}
          </section>
        </aside>
      </div>
      <HistoryDrawer />
      <div style={{ marginTop: 16 }}>
        <HowItWorks />
      </div>
      <PlayerDrawer />
      <CompareView />
    </>
  )
}
