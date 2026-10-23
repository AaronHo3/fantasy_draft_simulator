import { symmetricMax } from '../../lib/scale'
import { Tooltip } from '../ui/Tooltip'

export interface DivergingRow {
  id: string
  label: string
  /** Null draws no bar and prints a dash (missing is not zero). */
  value: number | null
  sublabel?: string
  color?: string
}

interface DivergingProps {
  rows: DivergingRow[]
  format: (v: number) => string
  unit: string
  selectedId?: string | null
  onSelect?: (id: string) => void
  /** Axis caption for each side. */
  negativeLabel?: string
  positiveLabel?: string
}

const signed = (v: number, format: (v: number) => string) => {
  const text = format(Math.abs(v))
  const zero = Number(text) === 0
  return zero ? format(0) : v > 0 ? `+${text}` : `−${text}`
}

/** Values around a zero line: positives extend right in the "good" tone, negatives left in the "bad" tone. */
export function Diverging({ rows, format, unit, selectedId, onSelect, negativeLabel = 'Below expectation', positiveLabel = 'Above expectation' }: DivergingProps) {
  const ext = symmetricMax(rows.map((r) => r.value ?? 0))
  const half = (v: number) => `${Math.min(50, (Math.abs(v) / ext) * 50)}%`
  return (
    <div className="diverging">
      <div className="diverging-axis" aria-hidden="true">
        <span>{negativeLabel}</span>
        <span>0</span>
        <span>{positiveLabel}</span>
      </div>
      <ol className="diverging-rows">
        {rows.map((r) => {
          const missing = r.value === null || !Number.isFinite(r.value)
          const v = missing ? 0 : (r.value as number)
          const sign = missing ? 'missing' : v > 0 ? 'positive' : v < 0 ? 'negative' : 'zero'
          const text = missing ? '—' : signed(v, format)
          const content = (
            <>
              <span className="div-label">
                <span className="bar-name">{r.label}</span>
                {r.sublabel && <span className="bar-sub">{r.sublabel}</span>}
              </span>
              <span className="div-track" aria-hidden="true">
                <span className="div-zero" />
                <span className={`div-bar ${sign}`} data-testid={`diverging-bar-${r.id}`} data-sign={sign} style={{ width: missing ? 0 : half(v), background: sign === 'positive' ? r.color : undefined }} />
              </span>
              <span className={`div-value ${sign}`}>{text}</span>
            </>
          )
          const tip = (
            <>
              <b>{r.label}</b>
              <br />
              {text} {unit}
            </>
          )
          return (
            <li key={r.id} className={selectedId === r.id ? 'selected' : undefined}>
              <Tooltip content={tip}>
                {onSelect ? (
                  <button type="button" className="div-row" aria-pressed={selectedId === r.id} aria-label={`${r.label}: ${text} ${unit}`} onClick={() => onSelect(r.id)}>
                    {content}
                  </button>
                ) : (
                  <span className="div-row" tabIndex={0} aria-label={`${r.label}: ${text} ${unit}`}>
                    {content}
                  </span>
                )}
              </Tooltip>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
