import { useEffect } from 'react'
import { categoryLabel, fmtCategoryValue, fmtNum, fmtPct } from '../../lib/format'
import { useSeasonStore } from '../../store/seasonStore'

export function ResultsTab({ sessionId }: { sessionId: string }) {
  const overview = useSeasonStore((s) => s.overview)
  const period = useSeasonStore((s) => s.period)
  const results = useSeasonStore((s) => s.results)
  const status = useSeasonStore((s) => s.resultsStatus)
  const error = useSeasonStore((s) => s.resultsError)
  const loadResults = useSeasonStore((s) => s.loadResults)
  const setPeriod = useSeasonStore((s) => s.setPeriod)
  const p = period ?? overview?.current_period ?? 1
  useEffect(() => {
    void loadResults(sessionId, p)
  }, [sessionId, p, loadResults])
  if (!overview) return null
  const cats = overview.league_categories
  const names = overview.manager_names
  const projected = new Map((results?.projected ?? []).map((m) => [`${m.home_manager_id}|${m.away_manager_id ?? ''}`, m.odds]))
  return (
    <div className="stack">
      <div className="row">
        <label htmlFor="results-period">Matchup period</label>
        <select id="results-period" value={p} onChange={(e) => setPeriod(Number(e.target.value))}>
          {Array.from({ length: 22 }, (_, i) => i + 1).map((n) => (
            <option key={n} value={n}>
              Week {n}
            </option>
          ))}
        </select>
        <span className="muted">{status === 'loading' ? 'Loading…' : ''}</span>
      </div>
      {error && <p className="error">{error}</p>}
      {results?.results.map((r) => {
        const odds = projected.get(`${r.home.manager_id}|${r.away?.manager_id ?? ''}`)
        return (
          <div key={`${r.home.manager_id}-${r.away?.manager_id ?? 'bye'}`} className="table-wrap">
            <table className="grid" aria-label={`${names[r.home.manager_id]} results`}>
              <thead>
                <tr>
                  <th scope="col">{r.away ? 'Actual (ESPN)' : 'Bye'}</th>
                  <th scope="col" className="num">Cats</th>
                  {cats.map((c) => (
                    <th key={c.key} scope="col" className="num">
                      {categoryLabel(c.key, cats)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[r.home, r.away].filter(Boolean).map((side) => (
                  <tr key={side!.manager_id}>
                    <th scope="row">{names[side!.manager_id] ?? side!.manager_id}</th>
                    <td className="num">{fmtNum(side!.cats_won, 1)}</td>
                    {cats.map((c) => {
                      const res = side!.results[c.key]
                      return (
                        <td key={c.key} className={`num ${res === 'WIN' ? 'pos' : res === 'LOSS' ? 'neg' : ''}`} title={res ?? ''}>
                          {fmtCategoryValue(c.key, side!.values[c.key])}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                {odds && (
                  <tr className="muted">
                    <th scope="row">Projected ({names[r.home.manager_id]} wins)</th>
                    <td className="num">{fmtNum(odds.expected_a, 1)}</td>
                    {cats.map((c) => (
                      <td key={c.key} className="num">
                        {fmtPct(odds.cat_p_a[c.key])}
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )
      })}
      {results && results.results.length === 0 && <p className="muted">ESPN has no pairings for week {p}.</p>}
    </div>
  )
}
