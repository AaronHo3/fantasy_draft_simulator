import { useState } from 'react'
import { categoryLabel, fmtNum, fmtPct, fmtSigned } from '../../lib/format'
import { probabilityTone } from '../../lib/scale'
import { useSeasonStore } from '../../store/seasonStore'
import { Diverging } from '../charts/Diverging'
import { Heatmap } from '../charts/Heatmap'
import { ChartFrame } from '../ui/ChartFrame'
import { Icon } from '../ui/Icon'

/** Power rankings as a team × category heatmap; pick a row to see that team's category profile as bars. */
export function PowerTab() {
  const overview = useSeasonStore((s) => s.overview)
  const [selected, setSelected] = useState<string | null>(null)
  if (!overview) return null
  const cats = overview.league_categories
  const byId = new Map(overview.power.map((t) => [t.manager_id, t]))
  const hasMovement = Object.values(overview.movement).some((v) => v !== 0)
  const sel = selected ? byId.get(selected) ?? null : overview.power.find((t) => t.is_user) ?? null
  const lead = [
    { key: 'rank', label: '#', numeric: true, render: (id: string) => String(byId.get(id)?.rank ?? '') },
    {
      key: 'team',
      label: 'Team',
      header: true,
      render: (id: string) => {
        const t = byId.get(id)
        return t ? `${t.name}${t.is_user ? ' (you)' : ''}` : id
      },
    },
    { key: 'cats', label: 'Cats / week', numeric: true, render: (id: string) => fmtNum(byId.get(id)?.expected_cats, 2) },
    {
      key: 'mv',
      label: 'Move',
      numeric: true,
      render: (id: string) => {
        const mv = overview.movement[id] ?? 0
        if (!hasMovement) return <span className="muted" title="Movement appears once two syncs can be compared">—</span>
        if (mv === 0) return <span className="muted">·</span>
        return (
          <span className={mv > 0 ? 'pos' : 'neg'}>
            <Icon name={mv > 0 ? 'arrow-up' : 'arrow-down'} size={12} /> {Math.abs(mv)}
          </span>
        )
      },
    },
    { key: 'ir', label: 'IR', numeric: true, render: (id: string) => String(byId.get(id)?.n_ir || '') },
  ]
  return (
    <div className="stack">
      <ChartFrame
        title="Power rankings"
        description="Expected categories won per week against the league-average opponent, over 600 simulated weeks with common random numbers. Each cell is the chance of winning that category."
        help="Rank is by expected categories per week. Movement compares against the previous sync, so it only appears once two syncs exist."
        legend={[{ label: 'you', swatch: 'mine' }]}
      >
        <Heatmap
          caption="Power rankings"
          testId="power-table"
          rows={overview.power.map((t) => ({ id: t.manager_id, label: t.name, className: t.is_user ? 'mine' : undefined }))}
          columns={cats.map((c) => ({ key: c.key, label: categoryLabel(c.key, cats), title: c.kind === 'ratio' ? `${c.numerator} ÷ ${c.denominator}` : c.higher_is_better ? undefined : 'lower is better' }))}
          value={(id, k) => byId.get(id)?.cat_win_prob[k]}
          format={fmtPct}
          tone={probabilityTone}
          lead={lead}
          scaleNote="0–100% chance to win the category against the league-average opponent; 40–60% is a toss-up."
          selectedId={sel?.manager_id ?? null}
          onSelect={setSelected}
        />
      </ChartFrame>
      {sel && (
        <ChartFrame
          title={`${sel.name}${sel.is_user ? ' (you)' : ''}: category profile`}
          description={`Roster z-score per category against the league pool. ${sel.n_players} players${sel.n_ir ? `, ${sel.n_ir} on IR` : ''}. Click another row above to switch teams.`}
          testId="power-profile"
        >
          <Diverging
            rows={cats.map((c) => ({ id: c.key, label: categoryLabel(c.key, cats), value: sel.z[c.key] ?? null, sublabel: `${fmtPct(sel.cat_win_prob[c.key])} to win${c.higher_is_better ? '' : ' · lower is better'}` }))}
            format={(v) => fmtSigned(v, 1).replace(/^[+-]/, '')}
            unit="z"
            negativeLabel="weakness"
            positiveLabel="strength"
          />
        </ChartFrame>
      )}
    </div>
  )
}
