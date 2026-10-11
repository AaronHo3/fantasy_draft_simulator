import { useState } from 'react'
import type { LeagueConfig } from '../../api/types'
import { PRIMITIVE_POSITIONS, SLOT_OPTIONS } from '../../lib/format'

interface Props {
  league: LeagueConfig
  onChange: (l: LeagueConfig) => void
}

export function SlotsEditor({ league, onChange }: Props) {
  const [toAdd, setToAdd] = useState<string>('UTIL')
  const slots = league.starting_slots ?? []
  const caps = league.position_caps ?? {}

  return (
    <fieldset>
      <legend>Roster slots and position caps</legend>
      <div className="row" style={{ marginBottom: 6 }}>
        <span>Starting slots ({slots.length}):</span>
        <div className="chips" role="list" aria-label="Starting slots">
          {slots.map((s, i) => (
            <span className="chip" key={`${s}-${i}`} role="listitem">
              {s}
              <button type="button" aria-label={`Remove ${s} slot ${i + 1}`} onClick={() => onChange({ ...league, starting_slots: slots.filter((_, k) => k !== i) })}>
                ×
              </button>
            </span>
          ))}
        </div>
        <select aria-label="Slot to add" value={toAdd} onChange={(e) => setToAdd(e.target.value)}>
          {SLOT_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button type="button" className="small" onClick={() => onChange({ ...league, starting_slots: [...slots, toAdd] })}>
          Add slot
        </button>
      </div>
      <div className="row" style={{ marginBottom: 6 }}>
        <label htmlFor="bench">Bench</label>
        <input id="bench" type="number" min={0} max={10} value={league.bench_slots} onChange={(e) => onChange({ ...league, bench_slots: Math.max(0, Number(e.target.value) || 0) })} />
        <label htmlFor="ir">IR</label>
        <input id="ir" type="number" min={0} max={5} value={league.ir_slots} onChange={(e) => onChange({ ...league, ir_slots: Math.max(0, Number(e.target.value) || 0) })} />
        <span className="muted">Rounds = starters + bench = {slots.length + league.bench_slots}</span>
      </div>
      <div className="row">
        <span>Primary-position caps (blank = none):</span>
        {PRIMITIVE_POSITIONS.map((p) => (
          <label key={p} className="nowrap">
            {p}{' '}
            <input
              type="number"
              min={0}
              max={20}
              style={{ width: '4em' }}
              aria-label={`Cap for ${p}`}
              value={caps[p] ?? ''}
              onChange={(e) => {
                const v = e.target.value
                const next = { ...caps }
                if (v === '') delete next[p]
                else next[p] = Math.max(0, Number(v) || 0)
                onChange({ ...league, position_caps: next })
              }}
            />
          </label>
        ))}
      </div>
    </fieldset>
  )
}
