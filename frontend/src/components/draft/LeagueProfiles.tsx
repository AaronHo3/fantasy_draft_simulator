import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { LeagueProfilesResponse } from '../../api/types'
import { categoryLabel, fmtCategoryValue, fmtInt, fmtSigned } from '../../lib/format'
import { idsMatch } from '../../lib/revision'
import { useDraftStore } from '../../store/draftStore'

/** Every manager's projected category totals and league rank, refreshed after each committed pick. */
export function LeagueProfiles() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const pending = useDraftStore((s) => s.pendingCommit)
  const [data, setData] = useState<LeagueProfilesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<'totals' | 'rank' | 'z'>('totals')
  const draftRev = state?.draft_revision ?? -1
  const leagueRev = state?.league_revision ?? -1
  const settled = pending === null

  useEffect(() => {
    if (!sessionId || draftRev < 0 || !settled) return
    let alive = true
    api
      .profiles(sessionId)
      .then((res) => {
        if (!alive) return
        setData(res)
        setError(null)
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      alive = false
    }
  }, [sessionId, draftRev, leagueRev, settled])

  if (!state) return null
  const current = data !== null && idsMatch(data.ids, state) && settled
  const cats = state.league.categories
  const n = state.league.managers.length
  return (
    <div>
      <div className="row" style={{ marginBottom: 6, gap: 8 }}>
        <span className="muted" style={{ fontSize: 12 }}>
          {data?.unit ?? ''}. Rank 1 is best in the league for that category (turnovers: fewest). Empty rosters count zero.
        </span>
        <span className="spacer" />
        <label>
          Show{' '}
          <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} aria-label="Profile display mode">
            <option value="totals">totals and rates</option>
            <option value="rank">league rank</option>
            <option value="z">z-score sums</option>
          </select>
        </label>
        {!current && <span className="badge">updating…</span>}
      </div>
      {error && <p className="callout error">Could not load league profiles: {error}</p>}
      <div className="table-wrap">
        <table className="grid" aria-label="League category profiles" data-testid="league-profiles" aria-busy={!current}>
          <thead>
            <tr>
              <th scope="col">Manager</th>
              <th scope="col" className="num">Players</th>
              {cats.map((c) => (
                <th scope="col" className="num" key={c.key} title={c.kind === 'ratio' ? `${c.numerator}/${c.denominator}` : undefined}>
                  {categoryLabel(c.key, cats)}
                </th>
              ))}
              <th scope="col" className="num" title="categories where this manager ranks in the top 3">Top-3 cats</th>
            </tr>
          </thead>
          <tbody>
            {(data?.managers ?? []).map((m) => (
              <tr key={m.manager_id} className={m.is_user ? 'mine' : undefined} data-testid="profile-row" data-manager-id={m.manager_id}>
                <th scope="row">
                  {m.name}
                  {m.is_user ? ' (you)' : ''}
                </th>
                <td className="num">{m.n_players}</td>
                {cats.map((c) => {
                  const rank = m.rank[c.key]
                  const tone = rank === null || rank === undefined ? '' : rank <= 3 ? 'pos' : rank > n - 3 ? 'neg' : ''
                  const v = m.totals[c.key]
                  const att = c.key === 'FG_PCT' ? m.attempts.FGA : c.key === 'FT_PCT' ? m.attempts.FTA : null
                  return (
                    <td className={`num ${tone}`} key={c.key} title={rank ? `rank ${rank} of ${n}` : 'no attempts yet'}>
                      {mode === 'rank' && (rank ?? '—')}
                      {mode === 'z' && fmtSigned(m.z[c.key], 1)}
                      {mode === 'totals' && (
                        <>
                          {fmtCategoryValue(c.key, v)}
                          {att !== null && v !== null && <span className="muted"> ({fmtInt(att)})</span>}
                          {rank ? <span className="muted"> #{rank}</span> : ''}
                        </>
                      )}
                    </td>
                  )
                })}
                <td className="num">{m.categories_top3}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
