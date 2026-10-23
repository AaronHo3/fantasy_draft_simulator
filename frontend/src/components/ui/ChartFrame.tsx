import type { ReactNode } from 'react'
import { Icon } from './Icon'
import { Tooltip } from './Tooltip'

export type Swatch = 'actual' | 'projected' | 'good' | 'bad' | 'mine' | 'team' | 'even'

export interface LegendItem {
  label: string
  swatch: Swatch
  color?: string
}

interface ChartFrameProps {
  title: string
  description?: ReactNode
  /** Short explanation shown in a tooltip behind the help icon. */
  help?: ReactNode
  legend?: LegendItem[]
  /** When set, the chart is replaced by this note naming the missing data. */
  unavailable?: ReactNode
  actions?: ReactNode
  children: ReactNode
  testId?: string
  className?: string
}

/** Titled container for a visual: heading, optional help tooltip, legend, and an explicit unavailable state. */
export function ChartFrame({ title, description, help, legend, unavailable, actions, children, testId, className }: ChartFrameProps) {
  return (
    <section className={`chart-frame${className ? ` ${className}` : ''}`} aria-label={title} data-testid={testId}>
      <header className="chart-head">
        <div className="chart-title">
          <h3>{title}</h3>
          {help && (
            <Tooltip content={help}>
              <button type="button" className="icon-btn help" aria-label={`About ${title}`}>
                <Icon name="help" size={14} />
              </button>
            </Tooltip>
          )}
        </div>
        {actions && <div className="chart-actions">{actions}</div>}
        {legend && legend.length > 0 && (
          <ul className="legend" aria-label="Legend">
            {legend.map((l) => (
              <li key={l.label}>
                <span className={`swatch ${l.swatch}`} style={l.color ? { background: l.color, borderColor: l.color } : undefined} aria-hidden="true" />
                {l.label}
              </li>
            ))}
          </ul>
        )}
      </header>
      {description && <p className="chart-desc">{description}</p>}
      {unavailable ? (
        <div className="chart-unavailable" role="note">
          <Icon name="info" size={16} />
          <span>{unavailable}</span>
        </div>
      ) : (
        <div className="chart-body">{children}</div>
      )}
    </section>
  )
}
