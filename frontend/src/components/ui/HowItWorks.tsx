import { Disclosure } from './Disclosure'

interface Step {
  title: string
  detail: string
}

const STEPS: Step[] = [
  { title: 'Projection snapshot', detail: 'Per-game lines for every player: learned model blended with ESPN, rookie and injury-return adjustments.' },
  { title: 'Rosters', detail: 'Draft log during the draft; ESPN roster moves after it (synced, never written back).' },
  { title: 'Standardise', detail: 'Roster totals per category become z-scores against the league pool; FG% and FT% stay makes ÷ attempts.' },
  { title: 'Simulate weeks', detail: 'Players play their real NBA schedule in daily-lineup mode; 600 simulated weeks with common random numbers.' },
  { title: 'Decide', detail: 'Draft: value above replacement, roster fit, survival. Season: matchup odds, power rankings, free-agent swaps.' },
]

/** Compact flow diagram of how numbers travel from projections to recommendations; expandable so it never crowds results. */
export function HowItWorks({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const w = 760
  const h = 150
  const n = STEPS.length
  const gap = 18
  const boxW = (w - gap * (n - 1)) / n
  return (
    <Disclosure summary="How this works" defaultOpen={defaultOpen} testId="how-it-works">
      <figure className="how-it-works">
        <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-labelledby="how-title" className="how-svg">
          <title id="how-title">Projections and rosters are standardised, simulated, and turned into draft and matchup decisions</title>
          <defs>
            <marker id="how-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" className="how-arrow" />
            </marker>
          </defs>
          {STEPS.map((s, i) => {
            const x = i * (boxW + gap)
            return (
              <g key={s.title} transform={`translate(${x} 0)`}>
                <rect x={0} y={28} width={boxW} height={94} rx={8} className={`how-box ${i === n - 1 ? 'last' : ''}`} />
                <text x={12} y={52} className="how-step">
                  {s.title}
                </text>
                <foreignObject x={10} y={60} width={boxW - 20} height={58}>
                  <p className="how-detail">{s.detail}</p>
                </foreignObject>
                {i < n - 1 && <line x1={boxW + 2} y1={75} x2={boxW + gap - 2} y2={75} className="how-line" markerEnd="url(#how-arrow)" />}
              </g>
            )
          })}
        </svg>
        <ol className="how-list">
          {STEPS.map((s) => (
            <li key={s.title}>
              <b>{s.title}.</b> {s.detail}
            </li>
          ))}
        </ol>
      </figure>
    </Disclosure>
  )
}
