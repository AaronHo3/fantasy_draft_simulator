import { useEffect } from 'react'
import { categoryLabel, fmtCategoryValue, fmtNum, fmtPct } from '../../lib/format'
import { useSeasonStore } from '../../store/seasonStore'
import { Icon } from '../ui/Icon'
import { EmptyState, ErrorState } from '../ui/States'

const PERIODS = Array.from({ length: 22 }, (_, i) => i + 1)

/** ESPN's actual category totals per pairing, with the model's pre-week odds underneath in a visibly different style. */
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
      <div className="filter-bar">
        <span className="field">
          <label htmlFor="results-period">Week</label>
          <select id="results-period" value={p} onChange={(e) => setPeriod(Number(e.target.value))}>
            {PERIODS.map((n) => (
              <option key={n} value={n}>
                Week {n}
              </option>
            ))}
          </select>
        </span>
        <span className="legend" aria-label="Legend">
          <span>
            <Icon name="check" size={12} className="pos" /> category won
          </span>
          <span>
            <Icon name="close" size={12} className="neg" /> lost
          </span>
          <span>
            <span className="swatch projected" aria-hidden="true" /> projected before the week
          </span>
        </span>
        <span className="status">{status === 'loading' ? 'Loading…' : ''}</span>
      </div>
      {error && <ErrorState title="Could not load results">{error}</ErrorState>}
      <div className="results-grid">
        {results?.results.map((r) => {
          const odds = projected.get(`${r.home.manager_id}|${r.away?.manager_id ?? ''}`)
          return (
            <div key={`${r.home.manager_id}-${r.away?.manager_id ?? 'bye'}`} className="table-wrap result-card">
              <table className="grid results" aria-label={`${names[r.home.manager_id]} results`}>
                <thead>
                  <tr>
                    <th scope="col">{r.away ? 'Actual (ESPN)' : 'Bye'}</th>
                    <th scope="col" className="num">Cats</th>
                    {cats.map((c) => (
                      <th key={c.key} scope="col" className="num" title={c.kind === 'ratio' ? `${c.numerator} ÷ ${c.denominator} over the week` : c.higher_is_better ? undefined : 'lower is better'}>
                        {categoryLabel(c.key, cats)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[r.home, r.away].filter(Boolean).map((side) => (
                    <tr key={side!.manager_id} className={r.winner === side!.manager_id ? 'won' : undefined}>
                      <th scope="row">
                        {names[side!.manager_id] ?? side!.manager_id}
                        {r.winner === side!.manager_id && <span className="badge ok">won</span>}
                      </th>
                      <td className="num">
                        <b>{fmtNum(side!.cats_won, 1)}</b>
                      </td>
                      {cats.map((c) => {
                        const res = side!.results[c.key]
                        return (
                          <td key={c.key} className={`num res ${res === 'WIN' ? 'pos' : res === 'LOSS' ? 'neg' : ''}`} title={res ?? 'not decided'}>
                            {res === 'WIN' && <Icon name="check" size={11} />}
                            {res === 'LOSS' && <Icon name="close" size={11} />}
                            {fmtCategoryValue(c.key, side!.values[c.key])}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                  {odds && (
                    <tr className="projected-row">
                      <th scope="row">
                        <span className="swatch projected" aria-hidden="true" /> Projected before the week: chance {names[r.home.manager_id]} wins each category · avg cats
                      </th>
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
      </div>
      {results && results.results.length === 0 && <EmptyState title={`ESPN has no pairings for week ${p}`}>Pick another week, or sync once ESPN publishes the schedule.</EmptyState>}
    </div>
  )
}
