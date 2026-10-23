import type { ReactNode } from 'react'
import type { Tone } from '../../lib/scale'

export interface HeatRow {
  id: string
  label: string
  /** Extra class for the row (e.g. "mine"). */
  className?: string
}

export interface HeatColumn {
  key: string
  label: string
  title?: string
}

export interface HeatLead {
  key: string
  label: string
  render: (rowId: string) => ReactNode
  numeric?: boolean
  /** The lead column that names the row (rendered as the row header and, when selectable, as the button). */
  header?: boolean
}

interface HeatmapProps {
  rows: HeatRow[]
  columns: HeatColumn[]
  value: (rowId: string, colKey: string) => number | null | undefined
  format: (v: number) => string
  tone: (v: number) => Tone
  /** Optional 0–1 intensity used for the cell shade; defaults to the value itself when in [0,1]. */
  intensity?: (v: number) => number
  scaleNote: ReactNode
  /** Leading columns rendered before the heat cells (rank, total). */
  lead?: HeatLead[]
  caption: string
  selectedId?: string | null
  onSelect?: (rowId: string) => void
  testId?: string
}

/** Team × category grid. Every cell carries its number; shade is a documented secondary cue. Rows select by click or keyboard. */
export function Heatmap({ rows, columns, value, format, tone, intensity, scaleNote, lead = [], caption, selectedId, onSelect, testId }: HeatmapProps) {
  const alpha = (v: number) => {
    const i = intensity ? intensity(v) : v
    return Math.max(0.08, Math.min(1, Math.abs(i - 0.5) * 2))
  }
  const headerIdx = Math.max(
    0,
    lead.findIndex((l) => l.header),
  )
  return (
    <div className="heatmap">
      <div className="table-wrap">
        <table className="grid heat" aria-label={caption} data-testid={testId}>
          <thead>
            <tr>
              {lead.map((l) => (
                <th key={l.key} scope="col" className={l.numeric ? 'num' : undefined}>
                  {l.label}
                </th>
              ))}
              {columns.map((c) => (
                <th key={c.key} scope="col" className="num" title={c.title}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.id}
                className={[r.className, selectedId === r.id ? 'selected' : ''].filter(Boolean).join(' ') || undefined}
                onClick={onSelect ? () => onSelect(r.id) : undefined}
                style={onSelect ? { cursor: 'pointer' } : undefined}
                aria-selected={onSelect ? selectedId === r.id : undefined}
              >
                {lead.map((l, i) => {
                  const content =
                    i === headerIdx && onSelect ? (
                      <button type="button" className="row-select" aria-pressed={selectedId === r.id} aria-label={`Show ${r.label}`} onClick={(e) => {
                        e.stopPropagation()
                        onSelect(r.id)
                      }}>
                        {l.render(r.id)}
                      </button>
                    ) : (
                      l.render(r.id)
                    )
                  return i === headerIdx ? (
                    <th key={l.key} scope="row" className={l.numeric ? 'num' : undefined}>
                      {content}
                    </th>
                  ) : (
                    <td key={l.key} className={l.numeric ? 'num' : undefined}>
                      {content}
                    </td>
                  )
                })}
                {columns.map((c) => {
                  const v = value(r.id, c.key)
                  if (v === null || v === undefined || !Number.isFinite(v)) {
                    return (
                      <td key={c.key} className="num heat-cell missing">
                        —
                      </td>
                    )
                  }
                  const t = tone(v)
                  return (
                    <td key={c.key} className={`num heat-cell ${t}`} style={{ ['--heat' as string]: alpha(v) }} title={`${c.label}: ${format(v)}`}>
                      {format(v)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="heat-scale">
        <span className="swatch bad" aria-hidden="true" /> unfavoured <span className="swatch even" aria-hidden="true" /> toss-up <span className="swatch good" aria-hidden="true" /> favoured · {scaleNote}
      </p>
    </div>
  )
}
