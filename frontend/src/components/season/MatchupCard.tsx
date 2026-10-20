import type { CategoryDef, MatchupPairView } from '../../api/types'
import { categoryLabel, fmtNum, fmtPct } from '../../lib/format'

interface MatchupCardProps {
  pair: MatchupPairView
  names: Record<string, string>
  categories: CategoryDef[]
  userId: string
  compact?: boolean
}

/** One pairing for the week: win/tie/loss odds, expected categories, and who is favored in each category. */
export function MatchupCard({ pair, names, categories, userId, compact = false }: MatchupCardProps) {
  const home = names[pair.home_manager_id] ?? pair.home_manager_id
  const away = pair.away_manager_id ? names[pair.away_manager_id] ?? pair.away_manager_id : null
  const isUser = pair.home_manager_id === userId || pair.away_manager_id === userId
  const cls = `matchup-card${isUser ? ' mine' : ''}${compact ? ' compact' : ''}`
  if (!away || !pair.odds) {
    return (
      <article className={cls} data-testid={isUser ? 'user-matchup' : undefined} aria-label={`${home} bye`}>
        <h3>
          {home}
          {pair.home_manager_id === userId ? ' (you)' : ''}
        </h3>
        <p className="muted">Bye week: no matchup in period {pair.period}.</p>
      </article>
    )
  }
  const o = pair.odds
  return (
    <article className={cls} data-testid={isUser ? 'user-matchup' : undefined} aria-label={`${home} vs ${away}`}>
      <h3>
        {home}
        {pair.home_manager_id === userId ? ' (you)' : ''} <span className="muted">vs</span> {away}
        {pair.away_manager_id === userId ? ' (you)' : ''}
      </h3>
      <div className="odds-row" aria-label="Week odds">
        <span className="odds win" title={`${home} wins the week`}>
          <b>{fmtPct(o.p_win_a)}</b> {home}
        </span>
        <span className="odds tie">
          <b>{fmtPct(o.p_tie)}</b> tie
        </span>
        <span className="odds loss" title={`${away} wins the week`}>
          <b>{fmtPct(o.p_win_b)}</b> {away}
        </span>
        <span className="spacer" />
        <span className="muted">
          expected {fmtNum(o.expected_a, 1)} – {fmtNum(o.expected_b, 1)} cats · likeliest {fmtNum(o.modal_score[0], 0)}–{fmtNum(o.modal_score[1], 0)}
          {o.games_a || o.games_b ? ` · games ${o.games_a}/${o.games_b}` : ''}
        </span>
      </div>
      <div className="cat-grid" role="list" aria-label="Category odds">
        {categories.map((c) => {
          const p = o.cat_p_a[c.key] ?? 0.5
          const favA = p >= 0.5
          return (
            <div key={c.key} role="listitem" className={`cat ${favA ? 'fav-a' : 'fav-b'}`} data-testid={`cat-${c.key}`} title={`${home} wins ${c.label} ${fmtPct(p)} of weeks`}>
              <span className="label">{categoryLabel(c.key, categories)}</span>
              <span className="bar" aria-hidden="true">
                <span className="fill" style={{ width: `${Math.round(p * 100)}%` }} />
              </span>
              <span className="num">{fmtPct(p)}</span>
            </div>
          )
        })}
      </div>
      {!compact && o.notes.length > 0 && (
        <ul className="notes muted">
          {o.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </article>
  )
}
