// Minimal hash router. The session id lives in the query string (`?session=<id>`) so a reload restores it:
//   http://127.0.0.1:5173/?session=abc123#/draft
import { useEffect, useState } from 'react'

export type Route = 'setup' | 'draft' | 'health' | 'recap' | 'season' | 'performers'

export interface Location {
  route: Route
  sessionId: string | null
}

const ROUTES: Route[] = ['setup', 'draft', 'health', 'recap', 'season', 'performers']

export function parseLocation(search: string, hash: string): Location {
  const sessionId = new URLSearchParams(search).get('session')
  const name = hash.replace(/^#\/?/, '').split('?')[0]
  const route = (ROUTES as string[]).includes(name) ? (name as Route) : sessionId ? 'draft' : 'setup'
  return { route, sessionId: sessionId || null }
}

export function buildUrl(route: Route, sessionId: string | null): string {
  const q = sessionId ? `?session=${encodeURIComponent(sessionId)}` : ''
  return `${window.location.pathname}${q}#/${route}`
}

export function navigate(route: Route, sessionId: string | null, replace = false): void {
  const url = buildUrl(route, sessionId)
  if (replace) window.history.replaceState(null, '', url)
  else window.history.pushState(null, '', url)
  window.dispatchEvent(new Event('locationchange'))
}

export function useLocation(): Location {
  const [loc, setLoc] = useState<Location>(() => parseLocation(window.location.search, window.location.hash))
  useEffect(() => {
    const update = () => setLoc(parseLocation(window.location.search, window.location.hash))
    window.addEventListener('hashchange', update)
    window.addEventListener('popstate', update)
    window.addEventListener('locationchange', update)
    return () => {
      window.removeEventListener('hashchange', update)
      window.removeEventListener('popstate', update)
      window.removeEventListener('locationchange', update)
    }
  }, [])
  return loc
}
