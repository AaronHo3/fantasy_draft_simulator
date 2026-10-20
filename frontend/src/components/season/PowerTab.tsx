import { categoryLabel, fmtNum, fmtPct } from '../../lib/format'
import { useSeasonStore } from '../../store/seasonStore'

export function PowerTab() {
  const overview = useSeasonStore((s) => s.overview)
  if (!overview) return null
  const cats = overview.league_categories
  return (
    <div className="table-wrap">
      <table className="grid" aria-label="Power rankings" data-testid="power-table">
        <thead>
          <tr>
            <th scope="col" className="num">#</th>
            <th scope="col">Team</th>
            <th scope="col" className="num">Cats / week</th>
            <th scope="col" className="num">Δ</th>
            {cats.map((c) => (
              <th key={c.key} scope="col" className="num">
                {categoryLabel(c.key, cats)}
              </th>
            ))}
            <th scope="col" className="num">IR</th>
          </tr>
        </thead>
        <tbody>
          {overview.power.map((t) => {
            const mv = overview.movement[t.manager_id] ?? 0
            return (
              <tr key={t.manager_id} className={t.is_user ? 'mine' : undefined}>
                <td className="num">{t.rank}</td>
                <th scope="row">
                  {t.name}
                  {t.is_user ? ' (you)' : ''}
                </th>
                <td className="num">{fmtNum(t.expected_cats, 2)}</td>
                <td className={`num ${mv > 0 ? 'pos' : mv < 0 ? 'neg' : 'muted'}`}>{mv > 0 ? `▲${mv}` : mv < 0 ? `▼${-mv}` : '·'}</td>
                {cats.map((c) => {
                  const p = t.cat_win_prob[c.key] ?? 0.5
                  return (
                    <td key={c.key} className={`num ${p >= 0.6 ? 'pos' : p <= 0.4 ? 'neg' : ''}`} title={`z ${fmtNum(t.z[c.key], 1)}`}>
                      {fmtPct(p)}
                    </td>
                  )
                })}
                <td className="num muted">{t.n_ir || ''}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
        Expected categories won per week against the league average opponent (600 simulated weeks, common random numbers). Δ is movement since the previous sync.
      </p>
    </div>
  )
}
