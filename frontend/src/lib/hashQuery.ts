// Page-level selections (tab, week, team) live in the hash query so a reload or a shared link
// restores them: `#/season?tab=power&week=3`. The session id stays in the real query string.

export type HashQuery = Record<string, string>

export function readHashQuery(hash: string): HashQuery {
  const q = hash.split('?')[1]
  if (!q) return {}
  const out: HashQuery = {}
  new URLSearchParams(q).forEach((v, k) => {
    out[k] = v
  })
  return out
}

/** New hash with `patch` applied; a null value removes the key. Keys are written in sorted order. */
export function withHashQuery(hash: string, patch: Record<string, string | null>): string {
  const route = hash.split('?')[0] || '#/'
  const next = { ...readHashQuery(hash) }
  for (const [k, v] of Object.entries(patch)) {
    if (v === null) delete next[k]
    else next[k] = v
  }
  const keys = Object.keys(next).sort()
  if (keys.length === 0) return route
  const params = new URLSearchParams()
  for (const k of keys) params.set(k, next[k])
  return `${route}?${params.toString()}`
}

/** Replace the current hash query in place (no history entry, no re-render of the router). */
export function replaceHashQuery(patch: Record<string, string | null>): void {
  const next = withHashQuery(window.location.hash, patch)
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${next}`)
}
