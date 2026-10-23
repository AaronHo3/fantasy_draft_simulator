import { useState } from 'react'
import { linear, niceMax } from '../../lib/scale'

export interface ScatterPoint {
  id: string
  label: string
  x: number | null | undefined
  y: number | null | undefined
  color?: string
  sublabel?: string
}

interface ScatterProps {
  points: ScatterPoint[]
  xLabel: string
  yLabel: string
  format: (v: number) => string
  selectedId?: string | null
  onSelect?: (id: string) => void
  width?: number
  height?: number
}

/** Actual vs expected: one point per row, diagonal equality line, hover/focus shows exact values. */
export function Scatter({ points, xLabel, yLabel, format, selectedId, onSelect, width = 520, height = 340 }: ScatterProps) {
  const [hover, setHover] = useState<string | null>(null)
  const valid = points.filter((p): p is ScatterPoint & { x: number; y: number } => typeof p.x === 'number' && typeof p.y === 'number' && Number.isFinite(p.x) && Number.isFinite(p.y))
  const pad = { l: 46, r: 16, t: 14, b: 38 }
  const vals = valid.flatMap((p) => [p.x, p.y])
  const lo = Math.min(0, ...vals)
  const hi = niceMax(Math.max(1, ...vals))
  const sx = linear([lo, hi], [pad.l, width - pad.r])
  const sy = linear([lo, hi], [height - pad.b, pad.t])
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => lo + t * (hi - lo))
  const active = hover ?? selectedId ?? null
  const activePt = valid.find((p) => p.id === active) ?? null
  return (
    <div className="scatter">
      <svg viewBox={`0 0 ${width} ${height}`} className="scatter-svg" role="group" aria-label={`${yLabel} against ${xLabel}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={sx(t)} x2={sx(t)} y1={pad.t} y2={height - pad.b} className="grid" />
            <line y1={sy(t)} y2={sy(t)} x1={pad.l} x2={width - pad.r} className="grid" />
            <text x={sx(t)} y={height - pad.b + 14} className="tick" textAnchor="middle">
              {format(t)}
            </text>
            <text x={pad.l - 6} y={sy(t) + 3} className="tick" textAnchor="end">
              {format(t)}
            </text>
          </g>
        ))}
        <line x1={sx(lo)} y1={sy(lo)} x2={sx(hi)} y2={sy(hi)} className="equality" data-testid="equality-line" />
        <text x={width - pad.r} y={height - 6} className="axis-label" textAnchor="end">
          {xLabel}
        </text>
        <text x={pad.l} y={10} className="axis-label">
          {yLabel}
        </text>
        {valid.map((p) => {
          const isActive = active === p.id
          return (
            <circle
              key={p.id}
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={isActive ? 7 : 5}
              className={`pt${isActive ? ' active' : ''}${p.y >= p.x ? ' over' : ' under'}`}
              style={{ fill: p.color }}
              data-testid="scatter-point"
              tabIndex={0}
              role={onSelect ? 'button' : undefined}
              aria-label={`${p.label}: ${yLabel} ${format(p.y)}, ${xLabel} ${format(p.x)}`}
              onMouseEnter={() => setHover(p.id)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(p.id)}
              onBlur={() => setHover(null)}
              onClick={() => onSelect?.(p.id)}
              onKeyDown={(e) => {
                if ((e.key === 'Enter' || e.key === ' ') && onSelect) {
                  e.preventDefault()
                  onSelect(p.id)
                }
              }}
            />
          )
        })}
        {activePt && (
          <text x={Math.min(sx(activePt.x) + 10, width - 90)} y={Math.max(sy(activePt.y) - 10, 20)} className="pt-label">
            {activePt.label}
          </text>
        )}
      </svg>
      <div className="scatter-readout" aria-live="polite">
        {activePt ? (
          <>
            <b>{activePt.label}</b> · {yLabel} {format(activePt.y)} · {xLabel} {format(activePt.x)} · {activePt.y >= activePt.x ? 'above' : 'below'} the line
          </>
        ) : (
          <span className="muted">Hover or focus a point. Points above the diagonal beat their expectation.</span>
        )}
      </div>
    </div>
  )
}
