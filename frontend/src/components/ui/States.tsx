import type { ReactNode } from 'react'
import { Icon } from './Icon'

interface StateProps {
  title: ReactNode
  children?: ReactNode
  action?: ReactNode
  testId?: string
}

/** Something is being fetched or computed. */
export function LoadingState({ title, children, testId }: StateProps) {
  return (
    <div className="state loading" role="status" aria-live="polite" data-testid={testId}>
      <span className="spinner" aria-hidden="true" />
      <div>
        <b>{title}</b>
        {children && <p>{children}</p>}
      </div>
    </div>
  )
}

/** Nothing to show yet: say what would fill it and how. */
export function EmptyState({ title, children, action, testId }: StateProps) {
  return (
    <div className="state empty" data-testid={testId}>
      <Icon name="info" size={18} />
      <div>
        <b>{title}</b>
        {children && <p>{children}</p>}
        {action && <div className="state-action">{action}</div>}
      </div>
    </div>
  )
}

/** A request failed: show the message and a way to retry. */
export function ErrorState({ title, children, action, testId }: StateProps) {
  return (
    <div className="state error" role="alert" data-testid={testId}>
      <Icon name="warning" size={18} />
      <div>
        <b>{title}</b>
        {children && <p>{children}</p>}
        {action && <div className="state-action">{action}</div>}
      </div>
    </div>
  )
}
