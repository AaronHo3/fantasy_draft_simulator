import type { SessionSummary } from '../../api/types'
import { fmtDate } from '../../lib/format'

interface SessionListProps {
  sessions: SessionSummary[] | null
  currentId: string | null
  onResume: (id: string) => void
  onDelete: (id: string) => void
}

export function SessionList({ sessions, currentId, onResume, onDelete }: SessionListProps) {
  if (sessions === null) return <p className="muted">Loading sessions…</p>
  if (sessions.length === 0) return <p className="muted">No sessions yet. Create one on the right.</p>
  return (
    <div className="table-wrap">
      <table className="grid">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Id</th>
            <th scope="col" className="num">
              Picks
            </th>
            <th scope="col">Updated</th>
            <th scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.id} data-testid="session-row" className={s.id === currentId ? 'mine' : undefined}>
              <td>{s.name}</td>
              <td className="mono">{s.id}</td>
              <td className="num">{s.n_commits ?? '—'}</td>
              <td className="nowrap">{fmtDate(s.updated_at)}</td>
              <td className="nowrap">
                <button type="button" className="small" data-testid="setup-resume" onClick={() => onResume(s.id)}>
                  Resume
                </button>{' '}
                <button type="button" className="small danger" onClick={() => onDelete(s.id)} aria-label={`Delete session ${s.name}`}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
