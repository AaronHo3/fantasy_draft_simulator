import { useState } from 'react'
import type { CategoryDef } from '../../api/types'

interface ExplainerProps {
  unitSizes: Record<string, number>
  benchmarkRates: Record<string, number>
  categories: CategoryDef[]
}

const NOUN: Record<string, string> = { PTS: 'points', REB: 'rebounds', AST: 'assists', STL: 'steals', BLK: 'blocks', FG3M: 'threes', TOV: 'turnovers' }

function unitText(key: string, size: number): string {
  const noun = NOUN[key]
  if (!noun) return ''
  const digits = size >= 1 ? 1 : 2
  return `${size.toFixed(digits)} ${noun} per game`
}

/** How contribution and expected are computed, with this league's actual unit sizes. */
export function Explainer({ unitSizes, benchmarkRates, categories }: ExplainerProps) {
  const [open, setOpen] = useState(false)
  const counting = categories.filter((c) => NOUN[c.key] && unitSizes[c.key] !== undefined)
  return (
    <section className="panel explainer" aria-label="How these numbers work">
      <button type="button" className="small" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid="explainer-toggle">
        {open ? '▾' : '▸'} How contribution and expected are calculated
      </button>
      {open && (
        <div className="stack" style={{ marginTop: 8 }}>
          <p>
            <b>Contribution</b> = Σ over categories of (per-game stat ÷ unit size) × games counted. Every category is put on one
            scale so they can be added: one unit is one standard deviation of per-game production across the league's player pool.
            A player who did not play is 0. Turnovers count against.
          </p>
          <p>
            <b>Expected</b> = the same formula applied to the player's projection (per game) × the games he actually played, so
            missing games are not held against him. <b>Vs expected</b> = contribution − expected.
          </p>
          <p>
            <b>FG% and FT%</b> are measured as shooting impact on the player's own attempts against the pool rates (
            {(benchmarkRates.FG_PCT * 100).toFixed(1)}% FG, {(benchmarkRates.FT_PCT * 100).toFixed(1)}% FT): makes above that rate
            count positive, below it negative, scaled like the other categories.
          </p>
          <p className="muted">In this league right now, one unit equals:</p>
          <ul className="units">
            {counting.map((c) => (
              <li key={c.key}>{unitText(c.key, unitSizes[c.key])}</li>
            ))}
          </ul>
          <p className="muted" style={{ fontSize: 12 }}>
            Expand any player row for the per-category breakdown that adds up to these totals. Baseline projections are the
            snapshot's per-game lines (learned model blended with ESPN, rookie and injury-return adjustments); players with only a
            prior have no baseline and are not ranked for overperformance.
          </p>
        </div>
      )}
    </section>
  )
}
