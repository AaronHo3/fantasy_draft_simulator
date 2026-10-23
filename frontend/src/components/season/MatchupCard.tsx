import type { CategoryDef, MatchupPairView, WeekResultView } from '../../api/types'
import { categoryLabel, fmtCategoryValue, fmtNum, fmtPct } from '../../lib/format'
import { ProbabilityPair, type PairRow } from '../charts/ProbabilityPair'
import { Tooltip } from '../ui/Tooltip'

interface MatchupCardProps {
  pair: MatchupPairView
  names: Record<string, string>
  categories: CategoryDef[]
  userId: string
  compact?: boolean
  /** ESPN's running totals for this pairing, when the results endpoint has them. */
  actual?: WeekResultView | null
}

/** One pairing for the week: projected winner with its chance as the key number, both sides' category odds. */
export function MatchupCard({ pair, names, categories, userId, compact = false, actual = null }: MatchupCardProps) {
  const home = names[pair.home_manager_id] ?? pair.home_manager_id
  const away = pair.away_manager_id ? names[pair.away_manager_id] ?? pair.away_manager_id : null
  const isUser = pair.home_manager_id === userId || pair.away_manager_id === userId
  const cls = `matchup-card${isUser ? ' mine' : ''}${compact ? ' compact' : ''}`
  if (!away || !pair.odds) {
    return (
      <article className={cls} data-testid={isUser ? 'user-matchup' : undefined} aria-label={`${home} bye`}>
        <h3 className="mc-title">
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
  const actualSide = (managerId: string) => (actual ? (actual.home.manager_id === managerId ? actual.home : actual.away?.manager_id === managerId ? actual.away : null) : null)
  const actWinner = actualSide(homeWins ? pair.home_manager_id : pair.away_manager_id!)
  const actLoser = actualSide(homeWins ? pair.away_manager_id! : pair.home_manager_id)
  const rows: PairRow[] = categories.map((c) => {
    const pHome = o.cat_p_a[c.key]
    const known = typeof pHome === 'number' && Number.isFinite(pHome)
    return {
      key: c.key,
      label: categoryLabel(c.key, categories),
      title: c.higher_is_better ? undefined : 'lower is better',
      pLeft: known ? (homeWins ? pHome : 1 - pHome) : null,
      leftValue: actWinner ? fmtCategoryValue(c.key, actWinner.values[c.key]) : null,
      rightValue: actLoser ? fmtCategoryValue(c.key, actLoser.values[c.key]) : null,
    }
  })
  return (
    <article className={cls} data-testid={isUser ? 'user-matchup' : undefined} aria-label={`${home} vs ${away}`}>
      <div className="mc-head">
        <h3 className="mc-title">
          {home}
          {pair.home_manager_id === userId ? ' (you)' : ''} <span className="muted">vs</span> {away}
          {pair.away_manager_id === userId ? ' (you)' : ''}
        </h3>
        {actual && (
          <span className="badge accent" title="ESPN running category totals for this week are shown under each category">
            ESPN actuals shown
          </span>
        )}
      </div>
      <div className="mc-odds">
        {compact ? (
          <span className="mc-winner" data-testid="projected-winner" title="The side that takes more than half the categories in most simulated weeks">
            <span className="mc-k">Projected winner</span>
            <span className="mc-v">
              <b className="mc-name">{winner}</b> <b className="mc-p">{fmtPct(pWinner)}</b>
            </span>
          </span>
        ) : (
          <Tooltip content="The side that takes more than half the categories in most simulated weeks">
            <span className="mc-winner" data-testid="projected-winner" tabIndex={0}>
              <span className="mc-k">Projected winner</span>
              <span className="mc-v">
                <b className="mc-name">{winner}</b> <b className="mc-p">{fmtPct(pWinner)}</b>
              </span>
            </span>
          </Tooltip>
        )}
        <span className="mc-rest muted" title="the other side's chance of winning the week, and the chance of a tie">
          {loser} {fmtPct(pLoser)} · tie {fmtPct(o.p_tie)}
        </span>
        <span className="mc-exp muted" title="mean categories won over all simulated weeks, not the score of any one week">
          avg categories {fmtNum(expWinner, 1)} – {fmtNum(expLoser, 1)} · most common score {fmtNum(homeWins ? o.modal_score[0] : o.modal_score[1], 0)}–{fmtNum(homeWins ? o.modal_score[1] : o.modal_score[0], 0)}
          {o.games_a || o.games_b ? ` · games ${homeWins ? o.games_a : o.games_b}/${homeWins ? o.games_b : o.games_a}` : ''}
        </span>
      </div>
      <ProbabilityPair
        leftName={winner}
        rightName={loser}
        rows={rows}
        compact={compact}
        valuesLabel="ESPN running totals this week (actual)"
        rowTestId={(k) => `cat-${k}`}
        rowClass={(k) => ((o.cat_p_a[k] ?? 0.5) >= 0.5 ? 'fav-a' : 'fav-b')}
        valuesNote="rates are makes ÷ attempts over the week"
      />
      {actual && !compact && <p className="mc-note muted">Numbers under each category are ESPN's running totals for the week (actual); bars and percentages are simulated odds (projected).</p>}
      {!compact && o.notes.length > 0 && (
        <ul className="mc-notes muted">
          {o.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </article>
  )
}
