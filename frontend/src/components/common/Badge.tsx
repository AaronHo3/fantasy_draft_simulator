import type { ReactNode } from 'react'

export type BadgeTone = 'neutral' | 'ok' | 'warn' | 'error' | 'accent' | 'loud'

interface BadgeProps {
  tone?: BadgeTone
  children: ReactNode
  title?: string
  testId?: string
}

export function Badge({ tone = 'neutral', children, title, testId }: BadgeProps) {
  const cls = tone === 'neutral' ? 'badge' : `badge ${tone}`
  return (
    <span className={cls} title={title} data-testid={testId}>
      {children}
    </span>
  )
}
