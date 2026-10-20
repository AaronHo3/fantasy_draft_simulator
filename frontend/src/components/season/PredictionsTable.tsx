import type { PredictionsResponse } from '../../api/types'
import { fmtDate, fmtNum, fmtPct } from '../../lib/format'
import { Badge } from '../common/Badge'

interface PredictionsTableProps {
  body: PredictionsResponse
  names: Record<string, string>
  userId: string
}

/** Every week's projected winner as it was frozen when the week started, scored against ESPN's result. */
export function PredictionsTable({ body, names, userId }: PredictionsTableProps) {
  const s = body.summary
  const name = (id: string | null) => (id === null ? '' : id === 'tie' ? 'tie' : names[id] ?? id)
  return (
    <div className="stack">
      <p data-testid="predictions-summary">
        <b>
          {s.n_correct} of {s.n_decided} decided weeks correct
        </b>
        {s.hit_rate !== null && s.hit_rate !== undefined ? ` (${fmtPct(s.hit_rate)})` : ''}
        {s.brier !== null && s.brier !== undefined ? ` · Brier ${fmtNum(s.brier, 3)} (0.25 = coin flip, lower is better)` : ''}
        <span className="muted"> · {s.n_predicted} matchups projected so far</span>
      </p>
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
                  <td>{p.predicted_winner ? name(p.predicted_winner) : <span className="muted">bye</span>}</td>
                  <td className="num">{p.p_winner === null || p.p_winner === undefined ? '' : fmtPct(p.p_winner)}</td>
                  <td className="num muted">
                    {p.expected_home === null || p.expected_home === undefined ? '' : `${fmtNum(p.expected_home, 1)} – ${fmtNum(p.expected_away, 1)}`}
                  </td>
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
      <p className="muted" style={{ fontSize: 11 }}>
        Projections are rewritten on every sync until the matchup period starts, then frozen, so roster moves after the fact cannot flatter the model. ESPN decides the actual winner; before ESPN marks it, the week is scored from category wins once it is over.
      </p>
    </div>
  )
}
