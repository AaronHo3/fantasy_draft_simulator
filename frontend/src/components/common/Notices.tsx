import { useDraftStore } from '../../store/draftStore'

export function Notices() {
  const notices = useDraftStore((s) => s.notices)
  const dismiss = useDraftStore((s) => s.dismissNotice)
  if (notices.length === 0) return null
  return (
    <div className="notices" aria-live="polite">
      {notices.map((n) => (
        <div key={n.id} className={`notice ${n.kind}`} role={n.kind === 'error' ? 'alert' : 'status'} data-testid="notice">
          <span className="kind">{n.kind}</span>
          <span className="text">{n.text}</span>
          <button type="button" className="small" onClick={() => dismiss(n.id)} aria-label="Dismiss notice">
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
