import { useState, type ReactNode } from 'react'
import { Icon } from './Icon'

interface DisclosureProps {
  summary: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  testId?: string
  /** Optional element rendered to the right of the summary, e.g. a status line. */
  aside?: ReactNode
}

/** Expandable help or detail section; closed by default so the results lead. */
export function Disclosure({ summary, children, defaultOpen = false, testId, aside }: DisclosureProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`disclosure${open ? ' open' : ''}`}>
      <div className="disclosure-head">
        <button type="button" className="disclosure-btn" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid={testId}>
          <Icon name={open ? 'chevron-down' : 'chevron-right'} size={14} />
          <span>{summary}</span>
        </button>
        {aside && <div className="disclosure-aside">{aside}</div>}
      </div>
      {open && <div className="disclosure-body">{children}</div>}
    </div>
  )
}
