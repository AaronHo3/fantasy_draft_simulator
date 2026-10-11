import type { LeagueConfig, Manager } from '../../api/types'
import { resizeManagers } from '../../lib/leagueDefaults'

interface Props {
  league: LeagueConfig
  onChange: (l: LeagueConfig) => void
}

function withManagers(league: LeagueConfig, managers: Manager[], userId: string): LeagueConfig {
  return {
    ...league,
    managers: managers.map((m) => ({ ...m, is_user: m.id === userId })),
    user_manager_id: userId,
    draft_order: managers.map((m) => m.id),
  }
}

export function ManagersEditor({ league, onChange }: Props) {
  const managers = league.managers
  const userIdx = managers.findIndex((m) => m.id === league.user_manager_id)

  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= managers.length) return
    const next = [...managers]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(withManagers(league, next, league.user_manager_id))
  }

  return (
    <fieldset>
      <legend>Managers and draft order</legend>
      <div className="row" style={{ marginBottom: 6 }}>
        <label htmlFor="n-managers">Managers</label>
        <input
          id="n-managers"
          type="number"
          min={2}
          max={30}
          data-testid="setup-manager-count"
          value={managers.length}
          onChange={(e) => {
            const n = Math.max(2, Math.min(30, Number(e.target.value) || 2))
            const next = resizeManagers(managers, n, league.user_manager_id)
            const user = next.find((m) => m.is_user) ?? next[0]
            onChange(withManagers(league, next, user.id))
          }}
        />
        <label htmlFor="draft-type">Draft type</label>
        <select id="draft-type" value={league.draft_type} onChange={(e) => onChange({ ...league, draft_type: e.target.value as LeagueConfig['draft_type'] })}>
          <option value="snake">Snake</option>
          <option value="linear">Linear</option>
          <option value="custom">Custom (edit order per pick later)</option>
        </select>
        <label>
          <input type="checkbox" checked={league.third_round_reversal} onChange={(e) => onChange({ ...league, third_round_reversal: e.target.checked })} />
          Third-round reversal
        </label>
        <span className="muted">You pick #{userIdx + 1} in round 1. Rows are the round-1 order.</span>
      </div>
      <div className="stack" role="list" aria-label="Managers">
        {managers.map((m, i) => (
          <div className="manager-row" key={m.id} role="listitem">
            <span className="muted num">{i + 1}.</span>
            <input
              type="text"
              aria-label={`Manager ${i + 1} name`}
              value={m.name}
              onChange={(e) => {
                const next = managers.map((x, k) => (k === i ? { ...x, name: e.target.value } : x))
                onChange(withManagers(league, next, league.user_manager_id))
              }}
            />
            <label className="nowrap">
              <input type="radio" name="user-team" checked={m.id === league.user_manager_id} onChange={() => onChange(withManagers(league, managers, m.id))} />
              my team
            </label>
            <button type="button" className="small" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move ${m.name} up`}>
              ↑
            </button>
            <button type="button" className="small" onClick={() => move(i, 1)} disabled={i === managers.length - 1} aria-label={`Move ${m.name} down`}>
              ↓
            </button>
          </div>
        ))}
      </div>
    </fieldset>
  )
}
