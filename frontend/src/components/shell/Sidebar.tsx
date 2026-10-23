import { fmtDate } from '../../lib/format'
import { buildUrl, type Route } from '../../lib/router'
import { Icon, type IconName } from '../ui/Icon'

export interface SidebarProps {
  route: Route
  sessionId: string | null
  sessionName: string | null
  isComplete: boolean
  leagueName: string | null
  syncedAt: string | null
  isDemo: boolean
}

interface NavItem {
  route: Route
  label: string
  icon: IconName
  afterDraft?: boolean
}

const NAV: NavItem[] = [
  { route: 'setup', label: 'Setup', icon: 'settings' },
  { route: 'draft', label: 'Draft', icon: 'clipboard' },
  { route: 'season', label: 'Season', icon: 'matchup', afterDraft: true },
  { route: 'performers', label: 'Performers', icon: 'chart', afterDraft: true },
  { route: 'recap', label: 'Recap', icon: 'trophy' },
  { route: 'health', label: 'Data health', icon: 'database' },
]

/** Charcoal navigation rail: brand, pages, and the session/league context pinned at the bottom. */
export function Sidebar({ route, sessionId, sessionName, isComplete, leagueName, syncedAt, isDemo }: SidebarProps) {
  return (
    <aside className="sidebar">
      <a className="brand" href={buildUrl(sessionId ? 'draft' : 'setup', sessionId)} aria-label="Courtside home">
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="22" height="22">
            <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.8" />
            <path d="M4.5 7.5c3 1.5 5 4 5 8.5M19.5 7.5c-3 1.5-5 4-5 8.5M2 12h20M12 2v20" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </span>
        <span className="brand-text">
          <span className="brand-name">Courtside</span>
          <span className="brand-sub">9-cat copilot</span>
        </span>
      </a>
      <nav aria-label="Main" className="nav">
        {NAV.filter((n) => !n.afterDraft || isComplete).map((n) => (
          <a key={n.route} href={buildUrl(n.route, sessionId)} aria-current={route === n.route ? 'page' : undefined} className="nav-item">
            <Icon name={n.icon} size={17} />
            <span>{n.label}</span>
          </a>
        ))}
      </nav>
      <div className="sidebar-ctx" role="complementary" aria-label="Session context">
        {isDemo && (
          <span className="demo-flag" title="Synthetic players and projections">
            <Icon name="warning" size={13} /> Demo data
          </span>
        )}
        {sessionId ? (
          <>
            <span className="ctx-line">
              <span className="ctx-key">Session</span>
              <span className="ctx-val" title={sessionId}>
                {sessionName ?? sessionId}
              </span>
            </span>
            <span className="ctx-line">
              <span className="ctx-key">League</span>
              <span className="ctx-val">{leagueName ?? (isComplete ? 'Not linked' : 'Draft in progress')}</span>
            </span>
            {leagueName && syncedAt && (
              <span className="ctx-line">
                <span className="ctx-key">Synced</span>
                <span className="ctx-val">{fmtDate(syncedAt).slice(0, 16)}</span>
              </span>
            )}
          </>
        ) : (
          <span className="ctx-line">
            <span className="ctx-val">No session open</span>
          </span>
        )}
      </div>
    </aside>
  )
}
