import { useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { ImportKind, ImportPreviewView } from '../../api/types'

const KINDS: { kind: ImportKind; label: string; hint: string }[] = [
  { kind: 'projections', label: 'Projections (per game)', hint: 'per-game rates with makes and attempts; replaces projections for matched players in a derived snapshot' },
  { kind: 'eligibility', label: 'ESPN eligibility', hint: 'primary position and eligible positions (PG;SG;…); source starting with "espn" counts as verified' },
  { kind: 'adp', label: 'ADP / ranks', hint: 'platform-labeled ADP or rank; non-ESPN platforms are flagged' },
  { kind: 'picks', label: 'Draft picks', hint: 'manager id or name plus player name; applied as an atomic batch of pick events' },
]

interface ImportPanelProps {
  sessionId: string | null
  lastSeq: number | null
  onApplied: (kind: ImportKind) => void
  notify: (kind: 'info' | 'warn' | 'error', text: string) => void
}

export function ImportPanel({ sessionId, lastSeq, onApplied, notify }: ImportPanelProps) {
  const [kind, setKind] = useState<ImportKind>('projections')
  const [text, setText] = useState('')
  const [preview, setPreview] = useState<ImportPreviewView | null>(null)
  const [skipErrors, setSkipErrors] = useState(false)
  const [busy, setBusy] = useState(false)

  const errorText = (e: unknown) => (e instanceof ApiError ? `${e.message}${e.detail.rows ? ` (rows ${String(e.detail.rows)})` : ''}` : e instanceof Error ? e.message : String(e))

  const loadFile = (file: File | undefined) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      setText(String(reader.result ?? ''))
      setPreview(null)
    }
    reader.readAsText(file)
  }

  const doPreview = async () => {
    if (!sessionId || !text.trim()) return
    setBusy(true)
    try {
      setPreview(await api.importPreview(sessionId, kind, text))
    } catch (e) {
      notify('error', `Preview failed: ${errorText(e)}`)
    } finally {
      setBusy(false)
    }
  }

  const doApply = async () => {
    if (!sessionId || !text.trim()) return
    setBusy(true)
    try {
      const res = await api.importApply(sessionId, kind, text, skipErrors, kind === 'picks' ? lastSeq : null)
      notify('info', `Imported ${res.applied_rows} ${kind} rows${res.skipped_rows ? `, skipped ${res.skipped_rows}` : ''}${res.snapshot_id ? `; session now uses snapshot ${res.snapshot_id}` : ''}.`)
      setPreview(null)
      setText('')
      onApplied(kind)
    } catch (e) {
      notify('error', `Import failed: ${errorText(e)}`)
    } finally {
      setBusy(false)
    }
  }

  const meta = KINDS.find((k) => k.kind === kind)

  return (
    <section className="panel" aria-labelledby="import-h" data-testid="import-panel">
      <div className="panel-head">
        <h3 id="import-h">CSV imports</h3>
      </div>
      {!sessionId && <p className="muted">Resume or create a session first; imports apply to a session.</p>}
      <div className="row" style={{ flexWrap: 'wrap', gap: 8 }}>
        <label>
          Kind{' '}
          <select value={kind} onChange={(e) => { setKind(e.target.value as ImportKind); setPreview(null) }} data-testid="import-kind">
            {KINDS.map((k) => (
              <option key={k.kind} value={k.kind}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <a href={`/api/templates/${kind}`} download={`${kind}_template.csv`}>
          Download {kind} template
        </a>
        <label>
          File <input type="file" accept=".csv,text/csv" onChange={(e) => loadFile(e.target.files?.[0])} />
        </label>
      </div>
      {meta && <p className="muted" style={{ fontSize: 12 }}>{meta.hint}. Units are stated in the template header; FG%/FT% need makes and attempts.</p>}
      <textarea
        aria-label="CSV text"
        data-testid="import-text"
        value={text}
        onChange={(e) => { setText(e.target.value); setPreview(null) }}
        rows={6}
        style={{ width: '100%', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}
        placeholder="Paste CSV here or choose a file"
      />
      <div className="row" style={{ gap: 8, marginTop: 6 }}>
        <button type="button" className="small" disabled={!sessionId || busy || !text.trim()} onClick={() => void doPreview()} data-testid="import-preview">
          Preview
        </button>
        <button type="button" className="small primary" disabled={!sessionId || busy || !preview || (preview.n_error > 0 && !skipErrors) || preview.n_ok === 0} onClick={() => void doApply()} data-testid="import-apply">
          Apply {preview ? `${preview.n_ok} rows` : ''}
        </button>
        <label>
          <input type="checkbox" checked={skipErrors} onChange={(e) => setSkipErrors(e.target.checked)} /> skip rows with errors
        </label>
      </div>
      {preview && (
        <div style={{ marginTop: 8 }}>
          <p className="muted" style={{ fontSize: 12 }}>
            {preview.n_ok} ok · {preview.n_error} with errors
            {preview.missing_columns.length > 0 && <span className="badge warn"> missing columns: {preview.missing_columns.join(', ')}</span>}
            {preview.notes.map((n) => (
              <span key={n}> · {n}</span>
            ))}
          </p>
          <div className="table-wrap" style={{ maxHeight: 260 }}>
            <table className="grid" data-testid="import-preview-table">
              <thead>
                <tr>
                  <th scope="col" className="num">Row</th>
                  <th scope="col">Matched player</th>
                  <th scope="col">Errors</th>
                  <th scope="col">Warnings</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.row} className={r.errors.length ? 'neg' : undefined}>
                    <td className="num">{r.row}</td>
                    <td>{r.matched_name ?? <span className="muted">unresolved</span>}</td>
                    <td>{r.errors.join('; ')}</td>
                    <td className="muted">{r.warnings.join('; ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
