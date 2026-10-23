import { useDraftStore } from '../../store/draftStore'
import { Icon } from '../ui/Icon'

export function Notices() {
  const notices = useDraftStore((s) => s.notices)
  const dismiss = useDraftStore((s) => s.dismissNotice)
  if (notices.length === 0) return null
  return (
    <div className="notices" aria-live="polite">
      {notices.map((n) => (
        <div key={n.id} className={`notice ${n.kind}`} role={n.kind === 'error' ? 'alert' : 'status'} data-testid="notice">
          <span className="kind" aria-label={n.kind}>
            <Icon name={n.kind === 'error' ? 'warning' : 'info'} size={15} />
          </span>
          <span className="text">{n.text}</span>
          <button type="button" className="small ghost icon-btn" onClick={() => dismiss(n.id)} aria-label="Dismiss notice">
            <Icon name="close" size={13} />
          </button>
        </div>
      ))}
    </div>
  )
}
