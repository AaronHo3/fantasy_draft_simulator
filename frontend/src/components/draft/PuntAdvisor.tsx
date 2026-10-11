import { useState } from 'react'
import { api } from '../../api/client'
import type { PuntAdvisorResponse, PuntKind, Strategy } from '../../api/types'
import { fmtPct, fmtSigned } from '../../lib/format'
import { idsMatch } from '../../lib/revision'
import { useDraftStore } from '../../store/draftStore'

/** Compares balanced vs single/double punts for the current roster; applying is always an explicit click. */
export function PuntAdvisor() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const state = useDraftStore((s) => s.state)
  const setStrategy = useDraftStore((s) => s.setStrategy)
  const notify = useDraftStore((s) => s.notify)
  const [result, setResult] = useState<PuntAdvisorResponse | null>(null)
  const [busy, setBusy] = useState(false)
  if (!state) return null
  const stale = result !== null && !idsMatch(result.ids, state)
  const keys = (state.league.categories ?? []).map((c) => c.key)

  const run = async () => {
    if (!sessionId) return
    setBusy(true)
    try {
      setResult(await api.puntAdvisor(sessionId, 8000))
    } catch (e) {
      notify('error', `Punt advisor failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }
  const apply = (punts: Record<string, string>) => {
    const next: Strategy = { ...state.strategy, punts: punts as Record<string, PuntKind>, mode: Object.keys(punts).length ? 'custom' : 'balanced' }
    void setStrategy(next)
  }

  return (
    <div style={{ marginTop: 10 }} data-testid="punt-advisor">
      <div className="row between">
        <h3 style={{ margin: 0 }}>Punt advisor</h3>
        <button type="button" className="small" disabled={busy || !sessionId || state.is_complete} onClick={() => void run()} data-testid="punt-advisor-run">
          {busy ? 'Simulating…' : result ? 'Re-run for current roster' : 'Compare punt scenarios'}
        </button>
      </div>
      <p className="muted small-text">
        Completes your remaining picks under each strategy, then scores every roster under the real rules (punted categories still count). Nothing is applied until you click Apply.
      </p>
      {stale && <p className="callout warn small-text">The draft moved since this analysis; re-run it.</p>}
      {result && (
        <>
          <div className="table-wrap">
            <table className="grid compact" aria-label="Punt scenarios">
              <thead>
                <tr>
                  <th scope="col">Scenario</th>
                  <th scope="col" className="num" title={result.objective_label}>Cats won / wk</th>
                  <th scope="col" className="num">vs balanced</th>
                  <th scope="col" className="num" title="categories with >= 55% win probability">Strong</th>
                  {keys.map((k) => (
                    <th scope="col" className="num" key={k}>
                      {k.replace('_PCT', '%').replace('FG3M', '3PM')}
                    </th>
                  ))}
                  <th scope="col">Likely next pick</th>
                  <th scope="col">
                    <span className="visually-hidden">Apply</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.scenarios.map((sc) => (
                  <tr key={sc.key} className={sc.is_current ? 'mine' : undefined} data-testid="punt-scenario" data-key={sc.key}>
                    <th scope="row">{sc.label}</th>
                    <td className="num">
                      {sc.objective.toFixed(2)} <span className="muted">±{sc.se.toFixed(2)}</span>
                    </td>
                    <td className={`num ${sc.delta_vs_balanced > 0.05 ? 'pos' : sc.delta_vs_balanced < -0.05 ? 'neg' : ''}`}>{fmtSigned(sc.delta_vs_balanced, 2)}</td>
                    <td className="num">{sc.strong_categories}</td>
                    {keys.map((k) => {
                      const p = sc.category_win_probs[k]
                      const punted = k in sc.punts
                      return (
                        <td key={k} className={`num ${punted ? 'muted' : p >= 0.55 ? 'pos' : p <= 0.45 ? 'neg' : ''}`} title={punted ? 'punted' : undefined}>
                          {punted ? `${fmtPct(p)}*` : fmtPct(p)}
                        </td>
                      )
                    })}
                    <td className="muted">{sc.likely_targets.join(', ')}</td>
                    <td>
                      {sc.is_current ? (
                        <span className="badge ok">active</span>
                      ) : (
                        <button type="button" className="small" onClick={() => apply(sc.punts)} disabled={stale}>
                          Apply
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="muted small-text" style={{ margin: '6px 0 0 16px' }}>
            {result.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
            <li>* punted category; its win probability is what you concede.</li>
          </ul>
        </>
      )}
    </div>
  )
}
