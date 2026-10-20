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
  const homeWins = o.p_win_a > o.p_win_b || (o.p_win_a === o.p_win_b && o.expected_a >= o.expected_b)
  const winner = homeWins ? home : away
  const loser = homeWins ? away : home
  const pWinner = homeWins ? o.p_win_a : o.p_win_b
  const pLoser = homeWins ? o.p_win_b : o.p_win_a
  const expWinner = homeWins ? o.expected_a : o.expected_b
  const expLoser = homeWins ? o.expected_b : o.expected_a
  return (
    <article className={cls} data-testid={isUser ? 'user-matchup' : undefined} aria-label={`${home} vs ${away}`}>
      <h3>
        {home}
        {pair.home_manager_id === userId ? ' (you)' : ''} <span className="muted">vs</span> {away}
        {pair.away_manager_id === userId ? ' (you)' : ''}
      </h3>
      <div className="odds-row" aria-label="Week odds">
        <span className="projected" data-testid="projected-winner" title="the side that takes more than half the categories in most simulated weeks">
          Projected winner: <b>{winner}</b> <b>{fmtPct(pWinner)}</b>
        </span>
        <span className="muted" title="the loser's chance of winning the week, and the chance of a tie">
          {loser} {fmtPct(pLoser)} · tie {fmtPct(o.p_tie)}
        </span>
        <span className="spacer" />
        <span className="muted" title="mean categories won over all simulated weeks, not the score of any one week">
          avg categories {fmtNum(expWinner, 1)} – {fmtNum(expLoser, 1)} · most common score {fmtNum(homeWins ? o.modal_score[0] : o.modal_score[1], 0)}–{fmtNum(homeWins ? o.modal_score[1] : o.modal_score[0], 0)}
          {o.games_a || o.games_b ? ` · games ${homeWins ? o.games_a : o.games_b}/${homeWins ? o.games_b : o.games_a}` : ''}
        </span>
      </div>
      <div className="cat-grid two-sided" role="list" aria-label="Category odds">
        <div className="cat head" aria-hidden="true">
          <span className="label" />
          <span className="side">{winner}</span>
          <span className="side">{loser}</span>
        </div>
        {categories.map((c) => {
          const pHome = o.cat_p_a[c.key] ?? 0.5
          const favA = pHome >= 0.5
          const pW = homeWins ? pHome : 1 - pHome
          const pL = 1 - pW
          return (
            <div key={c.key} role="listitem" className={`cat ${favA ? 'fav-a' : 'fav-b'}`} data-testid={`cat-${c.key}`} title={`${home} wins ${c.label} ${fmtPct(pHome)} of weeks`}>
              <span className="label">{categoryLabel(c.key, categories)}</span>
              <span className={`side ${pW >= 0.5 ? 'lead' : ''}`} data-testid={`cat-${c.key}-winner`}>
                <span className="bar" aria-hidden="true">
                  <span className="fill" style={{ width: `${Math.round(pW * 100)}%` }} />
                </span>
                <span className="num">{fmtPct(pW)}</span>
              </span>
              <span className={`side ${pL > 0.5 ? 'lead' : ''}`} data-testid={`cat-${c.key}-loser`}>
                <span className="bar" aria-hidden="true">
                  <span className="fill" style={{ width: `${Math.round(pL * 100)}%` }} />
                </span>
                <span className="num">{fmtPct(pL)}</span>
              </span>
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
