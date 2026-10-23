import type { ReactNode } from 'react'

export interface SegmentOption<T extends string> {
  id: T
  label: ReactNode
  testId?: string
  count?: ReactNode
}

interface SegmentedProps<T extends string> {
  value: T
  options: SegmentOption<T>[]
  onChange: (id: T) => void
  label: string
  /** 'tabs' renders as a tab list (role=tab); 'pill' renders a compact toggle group. */
  variant?: 'tabs' | 'pill'
}

/** Mutually exclusive choice rendered as accessible tabs or a pill toggle. */
export function Segmented<T extends string>({ value, options, onChange, label, variant = 'tabs' }: SegmentedProps<T>) {
  return (
    <div className={variant === 'tabs' ? 'tabs' : 'segmented'} role="tablist" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" role="tab" aria-selected={value === o.id} onClick={() => onChange(o.id)} data-testid={o.testId}>
          {o.label}
          {o.count !== undefined && o.count !== null && <span className="count">{o.count}</span>}
        </button>
      ))}
    </div>
  )
}
