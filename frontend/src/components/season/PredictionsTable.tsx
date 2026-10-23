import type { PredictionsResponse } from '../../api/types'
import { fmtDate, fmtNum, fmtPct } from '../../lib/format'
import { Badge } from '../common/Badge'
import { StatCard, StatRow } from '../ui/StatCard'

interface PredictionsTableProps {
  body: PredictionsResponse
  names: Record<string, string>
  userId: string
}

/** Every week's projected winner as it was frozen when the week started, scored against ESPN's result. */
export function PredictionsTable({ body, names, userId }: PredictionsTableProps) {
  const s = body.summary
  const name = (id: string | null) => (id === null ? '' : id === 'tie' ? 'tie' : names[id] ?? id)
  const hasRate = s.hit_rate !== null && s.hit_rate !== undefined
  const hasBrier = s.brier !== null && s.brier !== undefined
  return (
    <div className="stack">
      <p className="visually-hidden" data-testid="predictions-summary">
        {s.n_correct} of {s.n_decided} decided weeks correct{hasRate ? ` (${fmtPct(s.hit_rate)})` : ''}
        {hasBrier ? ` · Brier ${fmtNum(s.brier, 3)}` : ''} · {s.n_predicted} matchups projected so far
      </p>
      <StatRow>
        <StatCard label="Decided weeks called correctly" value={`${s.n_correct} / ${s.n_decided}`} detail={hasRate ? `${fmtPct(s.hit_rate)} hit rate` : 'no decided weeks yet'} tone={hasRate && (s.hit_rate ?? 0) >= 0.5 ? 'good' : 'neutral'} />
        <StatCard label="Brier score" value={hasBrier ? fmtNum(s.brier, 3) : '—'} detail="0.25 = coin flip, lower is better" />
        <StatCard label="Matchups projected" value={s.n_predicted} detail="frozen when each week starts" />
      </StatRow>
      <div className="table-wrap tall">
        <table className="grid" aria-label="Projection track record">
          <thead>
            <tr>
              <th scope="col" className="num">Week</th>
              <th scope="col">Matchup</th>
              <th scope="col">Projected winner</th>
              <th scope="col" className="num">Chance</th>
              <th scope="col" className="num">Avg cats</th>
              <th scope="col">Actual</th>
              <th scope="col">Result</th>
              <th scope="col">Frozen</th>
            </tr>
          </thead>
          <tbody>
            {body.predictions.map((p) => {
              const mine = p.home_manager_id === userId || p.away_manager_id === userId
              return (
                <tr key={`${p.period}-${p.home_manager_id}`} className={mine ? 'mine' : undefined} data-testid="prediction-row">
                  <td className="num">{p.period}</td>
                  <td>
                    {name(p.home_manager_id)}
                    {p.away_manager_id ? ` vs ${name(p.away_manager_id)}` : ' (bye)'}
                  </td>
                  <td>{p.predicted_winner ? <b>{name(p.predicted_winner)}</b> : <span className="muted">bye</span>}</td>
                  <td className="num">{fmtPct(p.p_winner)}</td>
                  <td className="num muted">{p.expected_home === null || p.expected_home === undefined ? '—' : `${fmtNum(p.expected_home, 1)} – ${fmtNum(p.expected_away, 1)}`}</td>
                  <td>
                    {p.actual_winner ? (
                      <>
                        {name(p.actual_winner)}
                        {p.actual_cats ? <span className="muted"> ({Object.values(p.actual_cats).map((v) => fmtNum(v, 1)).join(' – ')})</span> : null}
                      </>
                    ) : p.away_manager_id ? (
                      <span className="muted">pending</span>
                    ) : (
                      ''
                    )}
                  </td>
                  <td>
                    {p.correct === true && <Badge tone="ok">correct</Badge>}
                    {p.correct === false && <Badge tone="error">missed</Badge>}
                    {p.correct === null && p.predicted_winner && <span className="muted">open</span>}
                  </td>
                  <td className="muted" title={`recorded ${fmtDate(p.predicted_at)}`}>
                    {p.locked ? 'locked' : 'updating until the week starts'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="table-note">
        Projections are rewritten on every sync until the matchup period starts, then frozen, so roster moves after the fact cannot flatter the model. ESPN decides the actual winner; before ESPN marks it, the week is scored from category wins once it is over.
      </p>
    </div>
  )
}
