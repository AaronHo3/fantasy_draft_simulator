import { useEffect, type ReactNode } from 'react'
import { Notices } from './components/common/Notices'
import { buildUrl, navigate, useLocation, type Route } from './lib/router'
import { browserStorage, SESSION_KEY } from './lib/storage'
import { DraftScreen } from './screens/DraftScreen'
import { HealthScreen } from './screens/HealthScreen'
import { RecapScreen } from './screens/RecapScreen'
import { SeasonScreen } from './screens/SeasonScreen'
import { SetupScreen } from './screens/SetupScreen'
import { useDraftStore } from './store/draftStore'

const NAV: { route: Route; label: string; afterDraft?: boolean }[] = [
  { route: 'setup', label: 'Setup' },
  { route: 'draft', label: 'Draft' },
  { route: 'recap', label: 'Recap' },
  { route: 'season', label: 'Season', afterDraft: true },
  { route: 'health', label: 'Data health' },
]

export default function App() {
  const loc = useLocation()
  const sessionId = useDraftStore((s) => s.sessionId)
  const sessionName = useDraftStore((s) => s.sessionName)
  const loadSession = useDraftStore((s) => s.loadSession)
  const isComplete = useDraftStore((s) => s.state?.is_complete ?? false)

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
    default:
      screen = isComplete ? <RecapScreen /> : <DraftScreen />
  }

  return (
    <>
      <header className="app-header">
        <span className="brand">9-cat Draft Copilot</span>
        <nav aria-label="Main">
          {NAV.filter((n) => !n.afterDraft || isComplete).map((n) => (
            <a key={n.route} href={buildUrl(n.route, sessionId)} aria-current={loc.route === n.route ? 'page' : undefined}>
              {n.label}
            </a>
          ))}
        </nav>
        <span className="spacer" />
        {sessionId ? (
          <span className="muted">
            Session <span className="mono">{sessionId}</span>
            {sessionName ? ` · ${sessionName}` : ''}
          </span>
        ) : (
          <span className="muted">No session</span>
        )}
      </header>
      <main className="app-main">{screen}</main>
      <Notices />
    </>
  )
}
