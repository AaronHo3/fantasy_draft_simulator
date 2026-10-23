import type { ReactNode } from 'react'

export interface ContextChip {
  label: string
  value: ReactNode
  tone?: 'neutral' | 'accent' | 'amber' | 'warn' | 'demo'
  title?: string
}

interface PageHeaderProps {
  title: string
  description?: ReactNode
  chips?: ContextChip[]
  actions?: ReactNode
  /** Page-specific filters, rendered as a bar under the header. */
  filters?: ReactNode
}

/** Page title, one-line description, context chips (league, week, data source) and the page's filter bar. */
export function PageHeader({ title, description, chips, actions, filters }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header-row">
        <div className="page-title">
          <h1>{title}</h1>
          {description && <p className="page-desc">{description}</p>}
        </div>
        {(chips?.length || actions) && (
          <div className="page-side">
            {chips && chips.length > 0 && (
              <ul className="chips-ctx" aria-label="Context">
                {chips.map((c) => (
                  <li key={c.label} className={`ctx ${c.tone ?? 'neutral'}`} title={c.title}>
                    <span className="ctx-k">{c.label}</span>
                    <span className="ctx-v">{c.value}</span>
                  </li>
                ))}
              </ul>
            )}
            {actions && <div className="page-actions">{actions}</div>}
          </div>
        )}
      </div>
      {filters && <div className="filter-bar">{filters}</div>}
    </div>
  )
}
