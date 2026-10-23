import { useEffect, type ReactNode } from 'react'
import { Notices } from './components/common/Notices'
import { Sidebar } from './components/shell/Sidebar'
import { navigate, useLocation } from './lib/router'
import { browserStorage, SESSION_KEY } from './lib/storage'
import { DraftScreen } from './screens/DraftScreen'
import { HealthScreen } from './screens/HealthScreen'
import { PerformersScreen } from './screens/PerformersScreen'
import { RecapScreen } from './screens/RecapScreen'
import { SeasonScreen } from './screens/SeasonScreen'
import { SetupScreen } from './screens/SetupScreen'
import { useDraftStore } from './store/draftStore'
import { useSeasonStore } from './store/seasonStore'

export default function App() {
  const loc = useLocation()
  const sessionId = useDraftStore((s) => s.sessionId)
  const sessionName = useDraftStore((s) => s.sessionName)
  const loadSession = useDraftStore((s) => s.loadSession)
  const isComplete = useDraftStore((s) => s.state?.is_complete ?? false)
  const linked = useDraftStore((s) => s.state?.league.espn_league_id != null)
  const isDemo = useDraftStore((s) => s.snapshot?.is_demo ?? false)
  const leagueName = useSeasonStore((s) => s.overview?.league_name ?? null)
  const syncedAt = useSeasonStore((s) => s.overview?.synced_at ?? null)

  // Restore the session from ?session= or, failing that, from localStorage.
  useEffect(() => {
    const fromUrl = loc.sessionId
    const stored = browserStorage.get(SESSION_KEY)
    const id = fromUrl ?? stored
    if (id && id !== sessionId) void loadSession(id)
    if (!fromUrl && stored && loc.route !== 'setup') navigate(loc.route, stored, true)
  }, [loc.sessionId, loc.route, sessionId, loadSession])

  let screen: ReactNode
  switch (loc.route) {
    case 'setup':
      screen = <SetupScreen />
      break
    case 'health':
      screen = <HealthScreen />
      break
    case 'recap':
      screen = <RecapScreen />
      break
    case 'season':
      screen = <SeasonScreen />
      break
    case 'performers':
      screen = <PerformersScreen />
      break
    default:
      screen = isComplete ? <RecapScreen /> : <DraftScreen />
  }

  return (
    <div className="app-shell">
      <Sidebar
        route={loc.route}
        sessionId={sessionId}
        sessionName={sessionName}
        isComplete={isComplete}
        leagueName={linked ? leagueName ?? 'Linked to ESPN' : null}
        syncedAt={syncedAt}
        isDemo={isDemo}
      />
      <main className="app-main" id="main">
        {screen}
      </main>
      <Notices />
    </div>
  )
}
