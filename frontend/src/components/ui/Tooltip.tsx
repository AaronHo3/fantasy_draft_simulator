import { cloneElement, useId, useLayoutEffect, useRef, useState, type ReactElement, type ReactNode } from 'react'

interface TooltipProps {
  content: ReactNode
  children: ReactElement<Record<string, unknown>>
  /** Where the bubble sits relative to the trigger. */
  side?: 'top' | 'bottom'
}

const EDGE = 8

type Handler = ((x: unknown) => void) | undefined

/** Hover/focus tooltip with exact values; Esc dismisses; the bubble is kept inside the viewport. */
export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [shift, setShift] = useState(0)
  const bubble = useRef<HTMLSpanElement>(null)

  useLayoutEffect(() => {
    if (!open || !bubble.current) return
    const r = bubble.current.getBoundingClientRect()
    const vw = window.innerWidth
    let dx = 0
    if (r.left < EDGE) dx = EDGE - r.left
    else if (r.right > vw - EDGE) dx = vw - EDGE - r.right
    setShift(dx)
  }, [open, content])

  const chain = (name: string, fn: () => void) => (e: unknown) => {
    fn()
    ;(children.props[name] as Handler)?.(e)
  }
  const trigger = cloneElement(children, {
    'aria-describedby': open ? id : children.props['aria-describedby'],
    onMouseEnter: chain('onMouseEnter', () => setOpen(true)),
    onMouseLeave: chain('onMouseLeave', () => setOpen(false)),
    onFocus: chain('onFocus', () => setOpen(true)),
    onBlur: chain('onBlur', () => setOpen(false)),
    onKeyDown: (e: { key?: string }) => {
      if (e.key === 'Escape') setOpen(false)
      ;(children.props.onKeyDown as Handler)?.(e)
    },
  })
  return (
    <span className="tip-anchor">
      {trigger}
      {open && (
        <span role="tooltip" id={id} className={`tip tip-${side}`} ref={bubble} style={shift ? { transform: `translateX(calc(-50% + ${shift}px))` } : undefined}>
          {content}
        </span>
      )}
    </span>
  )
}
