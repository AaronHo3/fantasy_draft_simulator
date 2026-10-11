import type { LeagueConfig, ScoringFormat } from '../../api/types'
import { SCORING_FORMAT_LABELS } from '../../lib/leagueDefaults'

interface Props {
  league: LeagueConfig
  onChange: (l: LeagueConfig) => void
}

export function ScoringEditor({ league, onChange }: Props) {
  const cats = league.categories ?? []
  return (
    <fieldset>
      <legend>Scoring</legend>
      <div className="row" style={{ marginBottom: 6 }}>
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
      <div className="row">
        <span>Categories ({cats.length}):</span>
        <div className="chips" aria-label="Categories">
          {cats.map((c) => (
            <span className="chip" key={c.key} title={c.kind === 'ratio' ? `${c.numerator}/${c.denominator}` : c.higher_is_better ? 'higher is better' : 'lower is better'}>
              {c.label}
              {!c.higher_is_better ? ' (lower better)' : ''}
              {c.kind === 'ratio' ? ` (${c.numerator}/${c.denominator})` : ''}
            </span>
          ))}
        </div>
      </div>
    </fieldset>
  )
}
