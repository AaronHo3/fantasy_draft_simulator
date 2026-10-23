import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  /** Small line under the value: unit, comparison, or what the number means. */
  detail?: ReactNode
  tone?: 'neutral' | 'good' | 'bad' | 'accent' | 'amber'
  title?: string
  testId?: string
}

/** Key number with a label and one line of context. */
export function StatCard({ label, value, detail, tone = 'neutral', title, testId }: StatCardProps) {
  return (
    <div className={`stat-card ${tone}`} title={title} data-testid={testId}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {detail && <span className="stat-detail">{detail}</span>}
    </div>
  )
}

export function StatRow({ children }: { children: ReactNode }) {
  return <div className="stat-row">{children}</div>
}
