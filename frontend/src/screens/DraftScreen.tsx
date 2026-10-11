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
import { buildUrl } from '../lib/router'
import { selectRecCurrent, useDraftStore } from '../store/draftStore'

const NO_WARNINGS: string[] = []
type WorkTab = 'recommendations' | 'players'
type SideTab = 'roster' | 'categories' | 'strategy' | 'teams'
type MobilePane = 'find' | 'picks' | 'mine'

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
      <div className="empty-state" style={{ marginTop: 24 }}>
        <b>No draft open.</b>
        <p style={{ marginTop: 6 }}>
          <a href={buildUrl('setup', null)}>Create a league or resume a saved draft</a> to start recording picks.
        </p>
      </div>
    )
  }
  if (stateStatus === 'error') {
    return (
      <div className="callout error" role="alert">
        <p>
          Could not load draft {sessionId}: {stateError}
        </p>
        <button type="button" onClick={() => void refreshState()}>
          Try again
        </button>{' '}
        <a href={buildUrl('setup', null)}>Back to setup</a>
      </div>
    )
  }
  if (!hasState) return <p className="muted">Loading draft…</p>

  return (
    <>
      <Scoreboard />
      {!formatConfirmed && (
        <div className="callout warn" role="alert" data-testid="format-warning" style={{ marginBottom: 8 }}>
          Scoring format not confirmed: rankings assume <b>{scoringFormat}</b>.{' '}
          <button type="button" className="small" onClick={() => void confirmFormat()}>
            Confirm format
          </button>{' '}
          or change it in <a href={buildUrl('setup', sessionId)}>Setup</a>.
        </div>
      )}
      {warnings.length > 0 && (
        <div className="callout warn" role="status" style={{ marginBottom: 8 }}>
          {warnings.map((w) => (
            <div key={w}>{w}</div>
          ))}
        </div>
      )}
      {isComplete && (
        <div className="callout ok" role="status" style={{ marginBottom: 8 }}>
          Every pick is recorded. <a href={buildUrl('recap', sessionId)}>Open the recap</a> for final rosters and your category profile.
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
        <main className="col-work" data-mobile-hidden={pane !== 'picks'}>
          <RecommendationCard />
          <section className="panel" aria-label="Player workspace">
            <div className="tabs" role="tablist">
              <button type="button" role="tab" aria-selected={workTab === 'recommendations'} onClick={() => setWorkTab('recommendations')} data-testid="tab-recommendations">
                Recommendations{shortlistCount !== null && <span className="count">{shortlistCount}</span>}
              </button>
              <button type="button" role="tab" aria-selected={workTab === 'players'} onClick={() => setWorkTab('players')} data-testid="tab-players">
                All players{playersStatus === 'loading' ? <span className="count">loading…</span> : ''}
              </button>
            </div>
            {workTab === 'recommendations' ? <ShortlistTable /> : <AllPlayersTable />}
          </section>
        </main>
        <aside className="col-side" data-mobile-hidden={pane !== 'mine'}>
          <section className="panel" aria-label="My team and strategy">
            <div className="tabs" role="tablist">
              <button type="button" role="tab" aria-selected={sideTab === 'roster'} onClick={() => setSideTab('roster')} data-testid="tab-roster">
                My roster
              </button>
              <button type="button" role="tab" aria-selected={sideTab === 'categories'} onClick={() => setSideTab('categories')} data-testid="tab-categories">
                Categories
              </button>
              <button type="button" role="tab" aria-selected={sideTab === 'strategy'} onClick={() => setSideTab('strategy')} data-testid="tab-strategy">
                Strategy{activePunts > 0 && <span className="count">{activePunts} punt{activePunts > 1 ? 's' : ''}</span>}
              </button>
              <button type="button" role="tab" aria-selected={sideTab === 'teams'} onClick={() => setSideTab('teams')} data-testid="tab-teams">
                Teams
              </button>
            </div>
            {sideTab === 'roster' && <RosterPanel />}
            {sideTab === 'categories' && <CategoryProfileTable />}
            {sideTab === 'strategy' && <StrategyPanel />}
            {sideTab === 'teams' && <TeamsPanel />}
          </section>
        </aside>
      </div>
      <HistoryDrawer />
      <PlayerDrawer />
      <CompareView />
    </>
  )
}
