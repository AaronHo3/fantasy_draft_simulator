import { niceMax } from '../../lib/scale'
import { Tooltip } from '../ui/Tooltip'

export interface BarRow {
  id: string
  label: string
  /** Primary (actual) value. */
  value: number
  /** Secondary reference drawn as a thin outline bar (e.g. expected); null when there is none. */
  secondary?: number | null
  color?: string
  sublabel?: string
}

interface BarListProps {
  rows: BarRow[]
  format: (v: number) => string
  unit: string
  secondaryLabel?: string
  selectedId?: string | null
  onSelect?: (id: string) => void
  /** Fixed scale maximum; defaults to a nice rounding of the largest value. */
  max?: number
}

/** Aligned horizontal bars with the exact value beside each; click selects, hover shows the tooltip. */
export function BarList({ rows, format, unit, secondaryLabel = 'Expected', selectedId, onSelect, max }: BarListProps) {
  const top = max ?? niceMax(Math.max(0, ...rows.map((r) => Math.abs(r.value)), ...rows.map((r) => Math.abs(r.secondary ?? 0))))
  const pct = (v: number) => `${Math.min(100, (Math.abs(v) / top) * 100)}%`
  return (
    <ol className="barlist" aria-label="Bars">
      {rows.map((r) => {
        const tip = (
          <>
            <b>{r.label}</b>
            <br />
            {format(r.value)} {unit}
            {r.secondary !== null && r.secondary !== undefined ? (
              <>
                <br />
                {secondaryLabel}: {format(r.secondary)} {unit}
              </>
            ) : null}
          </>
        )
        const inner = (
          <>
            <span className="bar-label">
              <span className="bar-name">{r.label}</span>
              {r.sublabel && <span className="bar-sub">{r.sublabel}</span>}
            </span>
            <span className="bar-track" aria-hidden="true">
              <span className="bar-fill" style={{ width: pct(r.value), background: r.color }} />
              {r.secondary !== null && r.secondary !== undefined && <span className="bar-ref" style={{ width: pct(r.secondary) }} />}
            </span>
            <span className="bar-value">{format(r.value)}</span>
          </>
        )
        return (
          <li key={r.id} className={selectedId === r.id ? 'selected' : undefined}>
            <Tooltip content={tip}>
              {onSelect ? (
                <button type="button" className="bar-row" aria-pressed={selectedId === r.id} aria-label={`${r.label}: ${format(r.value)} ${unit}`} onClick={() => onSelect(r.id)}>
                  {inner}
                </button>
              ) : (
                <span className="bar-row" tabIndex={0} aria-label={`${r.label}: ${format(r.value)} ${unit}`}>
                  {inner}
                </span>
              )}
            </Tooltip>
          </li>
        )
      })}
    </ol>
  )
}
