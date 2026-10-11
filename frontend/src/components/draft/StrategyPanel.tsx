import type { PuntKind, RiskPreference, Strategy } from '../../api/types'
import { categoryLabel } from '../../lib/format'
import { useDraftStore } from '../../store/draftStore'
import { PuntAdvisor } from './PuntAdvisor'

type PuntChoice = 'none' | PuntKind

const SIM_PRESETS = [
  { ms: 1500, label: 'Quick · 1.5 s (coarse)' },
  { ms: 4000, label: 'Standard · 4 s' },
  { ms: 8000, label: 'Deep · 8 s' },
  { ms: 15000, label: 'Max · 15 s' },
]

function withPunt(s: Strategy, key: string, choice: PuntChoice): Strategy {
  const punts = Object.fromEntries(Object.entries(s.punts ?? {}).filter(([k]) => k !== key)) as Record<string, PuntKind>
  if (choice !== 'none') punts[key] = choice
  return { ...s, punts, mode: 'custom' }
}

function withWeight(s: Strategy, key: string, w: number): Strategy {
  const weights = { ...(s.weights ?? {}) }
  if (w === 1) delete weights[key]
  else weights[key] = w
  return { ...s, weights, mode: 'custom' }
}

export function StrategyPanel() {
  const state = useDraftStore((s) => s.state)
  const setStrategy = useDraftStore((s) => s.setStrategy)
  const saveStatus = useDraftStore((s) => s.saveStatus)
  if (!state) return null
  const strat = state.strategy
  const cats = state.league.categories ?? []
  const busy = saveStatus === 'saving'

  const commitNumber = (e: React.FocusEvent<HTMLInputElement> | React.KeyboardEvent<HTMLInputElement>, apply: (v: number) => Strategy) => {
    const v = Number((e.target as HTMLInputElement).value)
    if (!Number.isFinite(v)) return
    const next = apply(v)
    if (JSON.stringify(next) !== JSON.stringify(strat)) void setStrategy(next)
  }

  return (
    <section aria-labelledby="strategy-h" key={state.strategy_revision}>
      <div className="panel-head">
        <h3 id="strategy-h">Punts and weights</h3>
        <span className="muted small-text">re-ranks on every change</span>
      </div>
      <div className="row" style={{ marginBottom: 8 }} data-testid="sim-depth">
        <label htmlFor="sim-depth">Simulation depth</label>
        <select
          id="sim-depth"
          value={String(SIM_PRESETS.find((p) => p.ms === strat.sim_budget_ms)?.ms ?? 'custom')}
          disabled={busy}
          onChange={(e) => {
            const v = Number(e.target.value)
            if (Number.isFinite(v)) void setStrategy({ ...strat, sim_budget_ms: v })
          }}
        >
          {SIM_PRESETS.map((p) => (
            <option key={p.ms} value={p.ms}>
              {p.label}
            </option>
          ))}
          {!SIM_PRESETS.some((p) => p.ms === strat.sim_budget_ms) && <option value="custom">custom · {(strat.sim_budget_ms / 1000).toFixed(1)} s</option>}
        </select>
        <span className="muted small-text">
          wall-clock budget for the refined columns after each pick; keep it under the time between picks
        </span>
      </div>
      <div className="strategy-grid" role="group" aria-label="Punts and weights">
        <span className="head">Category</span>
        <span className="head">none</span>
        <span className="head">soft</span>
        <span className="head">fixed</span>
        <span className="head">weight</span>
        {cats.map((c) => {
          const cur: PuntChoice = strat.punts?.[c.key] ?? 'none'
          return (
            <PuntRow
              key={c.key}
              label={categoryLabel(c.key, cats)}
              catKey={c.key}
              value={cur}
              weight={strat.weights?.[c.key] ?? 1}
              disabled={busy}
              onPunt={(v) => void setStrategy(withPunt(strat, c.key, v))}
              onWeight={(e) => commitNumber(e, (v) => withWeight(strat, c.key, Math.max(0, v)))}
            />
          )
        })}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <label htmlFor="risk">Risk</label>
        <select id="risk" value={strat.risk} disabled={busy} onChange={(e) => void setStrategy({ ...strat, risk: e.target.value as RiskPreference })}>
          <option value="conservative">conservative</option>
          <option value="neutral">neutral</option>
          <option value="aggressive">aggressive</option>
        </select>
        <label htmlFor="soft-w">Soft punt weight</label>
        <input id="soft-w" type="number" min={0} max={1} step={0.05} defaultValue={strat.soft_punt_weight} disabled={busy} onBlur={(e) => commitNumber(e, (v) => ({ ...strat, soft_punt_weight: Math.min(1, Math.max(0, v)) }))} />
      </div>
      <details className="engine">
        <summary>Advanced simulation settings (engine only; never changes the draft)</summary>
      <div className="row" style={{ marginTop: 6 }}>
        <label htmlFor="sim-budget">Custom budget (ms)</label>
        <input id="sim-budget" type="number" min={100} max={30000} step={100} defaultValue={strat.sim_budget_ms} disabled={busy} onBlur={(e) => commitNumber(e, (v) => ({ ...strat, sim_budget_ms: Math.min(30000, Math.max(100, Math.round(v))) }))} />
        <label htmlFor="sim-scen">Scenarios</label>
        <input id="sim-scen" type="number" min={20} max={20000} step={20} defaultValue={strat.sim_scenarios} disabled={busy} onBlur={(e) => commitNumber(e, (v) => ({ ...strat, sim_scenarios: Math.min(20000, Math.max(20, Math.round(v))) }))} />
      </div>
      </details>
      <PuntAdvisor />
      <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        Fixed punt: the category counts nothing in the fast ranking. Soft punt: it counts at the soft weight. Punted categories still score in the weekly simulation.
      </p>
    </section>
  )
}

interface PuntRowProps {
  label: string
  catKey: string
  value: PuntChoice
  weight: number
  disabled: boolean
  onPunt: (v: PuntChoice) => void
  onWeight: (e: React.FocusEvent<HTMLInputElement>) => void
}

function PuntRow({ label, catKey, value, weight, disabled, onPunt, onWeight }: PuntRowProps) {
  const name = `punt-${catKey}`
  return (
    <>
      <span>
        {label}
        {value !== 'none' && <span className="badge warn" style={{ marginLeft: 4 }}>{value}</span>}
      </span>
      {(['none', 'soft', 'fixed'] as PuntChoice[]).map((v) => (
        <label key={v} className="nowrap">
          <input type="radio" name={name} value={v} checked={value === v} disabled={disabled} onChange={() => onPunt(v)} aria-label={`${label}: ${v} punt`} />
          <span className="visually-hidden">{v}</span>
        </label>
      ))}
      <input type="number" min={0} max={5} step={0.1} defaultValue={weight} disabled={disabled} aria-label={`${label} weight`} onBlur={onWeight} onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} />
    </>
  )
}
