import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { Icon } from '../ui/Icon'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
  onKeyDown?: (e: KeyboardEvent<HTMLDivElement>) => void
  testId?: string
}

/** Minimal accessible dialog: focus moves inside, Esc closes, backdrop click closes. */
export function Modal({ title, onClose, children, wide, onKeyDown, testId }: ModalProps) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const focusable = el.querySelector<HTMLElement>('[data-autofocus], button, select, input, textarea')
    focusable?.focus()
  }, [])
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className={wide ? 'modal wide' : 'modal'}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
        data-testid={testId}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.stopPropagation()
            onClose()
            return
          }
          onKeyDown?.(e)
        }}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button type="button" onClick={onClose} aria-label={`Close ${title}`}>
            <Icon name="close" size={14} /> Close
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
