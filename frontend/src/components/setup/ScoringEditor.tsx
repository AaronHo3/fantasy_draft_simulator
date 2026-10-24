import type { CategoryDef, LeagueConfig, ScoringFormat } from '../../api/types'
import { DEFAULT_NINE_CATEGORIES, SCORING_FORMAT_LABELS } from '../../lib/leagueDefaults'
import { Icon } from '../ui/Icon'

interface Props {
  league: LeagueConfig
  onChange: (l: LeagueConfig) => void
}

type Preset = 'nine' | 'eight' | 'custom'

const PRESETS: { id: Preset; label: string; keys: string[] | null }[] = [
  { id: 'nine', label: 'ESPN 9-cat (with turnovers)', keys: DEFAULT_NINE_CATEGORIES.map((c) => c.key) },
  { id: 'eight', label: '8-cat (no turnovers)', keys: DEFAULT_NINE_CATEGORIES.filter((c) => c.key !== 'TOV').map((c) => c.key) },
  { id: 'custom', label: 'Custom', keys: null },
]

function withKeys(keys: string[]): CategoryDef[] {
  return DEFAULT_NINE_CATEGORIES.filter((c) => keys.includes(c.key))
}

function presetFor(cats: CategoryDef[]): Preset {
  const keys = cats.map((c) => c.key)
  for (const p of PRESETS) {
    if (p.keys && p.keys.length === keys.length && p.keys.every((k) => keys.includes(k))) return p.id
  }
  return 'custom'
}

/** Scoring format, tie rule, lineup mode, and which categories the league scores (9-cat, 8-cat, or any subset). */
export function ScoringEditor({ league, onChange }: Props) {
  const cats = league.categories ?? []
  const active = new Set(cats.map((c) => c.key))
  const preset = presetFor(cats)
  const toggle = (key: string) => {
    const next = DEFAULT_NINE_CATEGORIES.filter((c) => (c.key === key ? !active.has(key) : active.has(c.key)))
    onChange({ ...league, categories: next })
  }
  return (
    <fieldset>
      <legend>Scoring</legend>
      <div className="row" style={{ marginBottom: 8 }}>
        <label htmlFor="fmt">Scoring format</label>
        <select id="fmt" data-testid="setup-format" value={league.scoring_format} onChange={(e) => onChange({ ...league, scoring_format: e.target.value as ScoringFormat })}>
          {(Object.keys(SCORING_FORMAT_LABELS) as ScoringFormat[]).map((k) => (
            <option key={k} value={k}>
              {SCORING_FORMAT_LABELS[k]}
            </option>
          ))}
        </select>
        {league.scoring_format === 'h2h_each_category' && (
          <>
            <label htmlFor="ties">Ties</label>
            <select
              id="ties"
              data-testid="setup-ties"
              value={String(league.tie_rule?.each_category_tie_value ?? 0.5)}
              onChange={(e) => onChange({ ...league, tie_rule: { ...(league.tie_rule ?? { matchup_tie_breaker: 'none', zero_attempts: 'unknown' }), each_category_tie_value: Number(e.target.value) } })}
            >
              <option value="0.5">allowed: a tied category counts half (ESPN W-L-T)</option>
              <option value="0">allowed: a tied category counts nothing</option>
            </select>
          </>
        )}
        <label htmlFor="lineup">Lineup</label>
        <select id="lineup" value={league.lineup_mode} onChange={(e) => onChange({ ...league, lineup_mode: e.target.value as LeagueConfig['lineup_mode'] })}>
          <option value="weekly">Weekly</option>
          <option value="daily">Daily</option>
        </select>
        <label>
          <input type="checkbox" checked={league.strict_eligibility} onChange={(e) => onChange({ ...league, strict_eligibility: e.target.checked })} />
          Strict eligibility (exclude unverified)
        </label>
      </div>
      <div className="row" style={{ marginBottom: 6 }}>
        <label htmlFor="cat-preset">Category preset</label>
        <select
          id="cat-preset"
          data-testid="setup-category-preset"
          value={preset}
          onChange={(e) => {
            const p = PRESETS.find((x) => x.id === e.target.value)
            if (p?.keys) onChange({ ...league, categories: withKeys(p.keys) })
          }}
        >
          {PRESETS.map((p) => (
            <option key={p.id} value={p.id} disabled={p.id === 'custom'}>
              {p.label}
            </option>
          ))}
        </select>
        <span className="muted small-text">
          {cats.length} scored categor{cats.length === 1 ? 'y' : 'ies'} · click a chip to toggle it
        </span>
      </div>
      <div className="chips" role="group" aria-label="Scored categories">
        {DEFAULT_NINE_CATEGORIES.map((c) => {
          const on = active.has(c.key)
          const hint = c.kind === 'ratio' ? `${c.numerator} ÷ ${c.denominator}` : c.higher_is_better ? 'higher is better' : 'lower is better'
          return (
            <button key={c.key} type="button" aria-pressed={on} onClick={() => toggle(c.key)} title={`${hint}${on ? '' : ' · not scored'}`} data-testid={`setup-cat-${c.key}`}>
              {on ? <Icon name="check" size={12} /> : <Icon name="minus" size={12} />}
              {c.label}
              {!c.higher_is_better ? ' (lower better)' : ''}
            </button>
          )
        })}
      </div>
      <p className="table-note">Only scored categories count in rankings, simulations, the category profile and the performers' contribution. Unscored stats still show in player lines, labelled as not scored.</p>
    </fieldset>
  )
}
