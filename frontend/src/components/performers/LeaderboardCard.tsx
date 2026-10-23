import type { PerformerRow } from '../../api/types'
import { fmtNum, fmtSigned, positionsText } from '../../lib/format'
import { teamColor } from '../../lib/teamColors'
import { Portrait } from './Portrait'

interface LeaderboardCardProps {
  title: string
  tooltip: string
  rows: PerformerRow[]
  metric: 'contribution' | 'over_expected'
  limit?: number
  testId?: string
}

/** Top-N card: leader highlighted, actual vs expected bars, team-colored accents. */
export function LeaderboardCard({ title, tooltip, rows, metric, limit = 5, testId }: LeaderboardCardProps) {
  const top = rows.slice(0, limit)
  const max = Math.max(1e-9, ...top.map((r) => Math.abs(metric === 'contribution' ? r.contribution : (r.over_expected ?? 0))), ...top.map((r) => Math.abs(r.expected_contribution ?? 0)))
  return (
    <section className="panel leaderboard" aria-label={title} data-testid={testId}>
      <div className="panel-head">
        <h2>
          {title}{' '}
          <span className="info" title={tooltip} aria-label={tooltip} role="img">
            ⓘ
          </span>
        </h2>
      </div>
      {top.length === 0 ? (
        <p className="muted">No qualifying players.</p>
      ) : (
        <ol className="leaders">
          {top.map((r, i) => {
            const color = teamColor(r.player.team)
            const value = metric === 'contribution' ? r.contribution : (r.over_expected ?? 0)
            const expected = r.expected_contribution ?? 0
            return (
              <li key={r.player.player_id} className={i === 0 ? 'lead' : undefined} style={{ borderLeftColor: color.primary }}>
                <span className="rank">{i + 1}</span>
                <Portrait name={r.player.name} espnId={r.player.espn_id} team={r.player.team} size={i === 0 ? 56 : 40} />
                <span className="who">
                  <b>{r.player.name}</b>
                  <span className="muted">
                    {r.player.team ?? '—'} · {positionsText(r.player.eligible_positions)} · {r.games} GP
                    {r.flags.length ? ` · ${r.flags.join(', ')}` : ''}
                  </span>
                  {metric === 'contribution' ? (
                    <span className="bars" aria-hidden="true">
                      <span className="bar actual" style={{ width: `${Math.min(100, (Math.abs(r.contribution) / max) * 100)}%`, background: color.primary }} />
                      {r.expected_contribution !== null && <span className="bar expected" style={{ width: `${Math.min(100, (Math.abs(expected) / max) * 100)}%` }} />}
                    </span>
                  ) : (
                    <span className="bars" aria-hidden="true">
                      <span className={`bar ${value >= 0 ? 'actual' : 'under'}`} style={{ width: `${Math.min(100, (Math.abs(value) / max) * 100)}%`, background: value >= 0 ? color.primary : undefined }} />
                    </span>
                  )}
                </span>
                <span className="value">
                  <b>{metric === 'contribution' ? fmtNum(r.contribution, 1) : fmtSigned(r.over_expected, 1)}</b>
                  <span className="muted">{metric === 'contribution' ? `exp ${r.expected_contribution === null ? '—' : fmtNum(r.expected_contribution, 1)}` : `of ${fmtNum(r.contribution, 1)}`}</span>
                </span>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
