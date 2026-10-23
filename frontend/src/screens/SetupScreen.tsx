import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { LeagueConfig, SessionSummary, SnapshotMeta } from '../api/types'
import { KeepersTradesEditor } from '../components/setup/KeepersTradesEditor'
import { LeagueJsonEditor } from '../components/setup/LeagueJsonEditor'
import { ManagersEditor } from '../components/setup/ManagersEditor'
import { ScoringEditor } from '../components/setup/ScoringEditor'
import { ImportPanel } from '../components/setup/ImportPanel'
import { SessionList } from '../components/setup/SessionList'
import { SlotsEditor } from '../components/setup/SlotsEditor'
import { SnapshotPicker } from '../components/setup/SnapshotPicker'
import { PageHeader } from '../components/ui/PageHeader'
import { newIdempotencyKey } from '../lib/format'
import { defaultLeague, validateLeague } from '../lib/leagueDefaults'
import { buildUrl, navigate } from '../lib/router'
import { useDraftStore } from '../store/draftStore'

export function SetupScreen() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [sessionsError, setSessionsError] = useState<string | null>(null)
  const [snapshots, setSnapshots] = useState<SnapshotMeta[]>([])
  const [league, setLeague] = useState<LeagueConfig>(() => defaultLeague())
  const [sessionName, setSessionName] = useState('')
  const [snapshotId, setSnapshotId] = useState<string | null>(null)
  const [confirmFormat, setConfirmFormat] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const notify = useDraftStore((s) => s.notify)
  const currentSessionId = useDraftStore((s) => s.sessionId)
  const clearSession = useDraftStore((s) => s.clearSession)
  const lastSeq = useDraftStore((s) => s.state?.last_seq ?? null)
  const loadSession = useDraftStore((s) => s.loadSession)
  const refreshState = useDraftStore((s) => s.refreshState)

  const refresh = useCallback(async () => {
    try {
      const [ss, snaps] = await Promise.all([api.listSessions(), api.snapshots()])
      setSessions(ss)
      setSnapshots(snaps)
      setSessionsError(null)
      setSnapshotId((cur) => cur ?? snaps[0]?.snapshot_id ?? null)
    } catch (e) {
      setSessionsError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const create = async () => {
    const errs = validateLeague(league)
    setErrors(errs)
    if (errs.length) return
    setBusy(true)
    try {
      const summary = await api.createSession({
        league: { ...league, format_confirmed: false, draft_order: league.managers.map((m) => m.id) },
        snapshot_id: snapshotId,
        name: sessionName.trim() || league.name,
      })
      if (confirmFormat) {
        await api.appendEvent(summary.id, { type: 'format_confirmed', payload: {}, idempotency_key: newIdempotencyKey(), source: 'manual' })
      }
      navigate('draft', summary.id)
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)])
    } finally {
      setBusy(false)
    }
  }

  const importFile = async (file: File) => {
    setBusy(true)
    try {
      const text = await file.text()
      const body = JSON.parse(text) as Record<string, unknown>
      const summary = await api.importSession(body)
      notify('info', `Imported session ${summary.id}`)
      navigate('draft', summary.id)
    } catch (e) {
      notify('error', `Import failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: string) => {
    if (!window.confirm(`Delete session ${id}? This cannot be undone.`)) return
    try {
      await api.deleteSession(id)
      if (id === currentSessionId) clearSession()
      await refresh()
    } catch (e) {
      notify('error', `Delete failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const selectedSnapshot = snapshots.find((s) => s.snapshot_id === snapshotId) ?? null

  return (
    <>
      <PageHeader title="Setup" description="Resume a saved draft, import a session, or describe a new league: scoring, managers, lineup slots, keepers and traded picks." />
      <div className="setup-layout">
      <div className="stack">
        <section className="panel" aria-labelledby="sessions-h">
          <div className="panel-head">
            <h2 id="sessions-h">Sessions</h2>
            <button type="button" className="small" onClick={() => void refresh()}>
              Refresh
            </button>
          </div>
          {sessionsError && <p className="callout error">Backend unreachable: {sessionsError}</p>}
          <SessionList sessions={sessions} currentId={currentSessionId} onResume={(id) => navigate('draft', id)} onDelete={(id) => void remove(id)} />
          <div className="row" style={{ marginTop: 8 }}>
            <label>
              Import session JSON{' '}
              <input
                type="file"
                accept="application/json,.json"
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void importFile(f)
                  e.target.value = ''
                }}
              />
            </label>
          </div>
          <p className="muted" style={{ marginTop: 6 }}>
            <a href={buildUrl('health', currentSessionId)}>Data health</a> · snapshots, provenance and freshness.
          </p>
          <ImportPanel
            sessionId={currentSessionId}
            lastSeq={lastSeq}
            notify={notify}
            onApplied={(kind) => {
              if (kind === 'picks') void refreshState()
              else if (currentSessionId) void loadSession(currentSessionId)
            }}
          />
        </section>
        {currentSessionId && (
          <section className="panel" aria-labelledby="current-h">
            <h2 id="current-h">Current session (advanced)</h2>
            <LeagueJsonEditor />
          </section>
        )}
      </div>

      <section className="panel" aria-labelledby="new-h">
        <h2 id="new-h">New session</h2>
        <div className="form-grid" style={{ marginBottom: 8 }}>
          <label htmlFor="league-name">League name</label>
          <input id="league-name" data-testid="setup-league-name" value={league.name} onChange={(e) => setLeague({ ...league, name: e.target.value })} />
          <label htmlFor="session-name">Session name</label>
          <input id="session-name" value={sessionName} placeholder="defaults to league name" onChange={(e) => setSessionName(e.target.value)} />
        </div>

        <SnapshotPicker snapshots={snapshots} value={snapshotId} onChange={setSnapshotId} />
        <ScoringEditor league={league} onChange={setLeague} />

        <div className={confirmFormat ? 'confirm-format done' : 'confirm-format'} style={{ marginBottom: 8 }}>
          <label>
            <input type="checkbox" data-testid="setup-confirm-format" checked={confirmFormat} onChange={(e) => setConfirmFormat(e.target.checked)} />
            Confirm your scoring format: this league scores as "{league.scoring_format}". Rankings depend on it; the draft screen warns until confirmed.
          </label>
        </div>

        <ManagersEditor league={league} onChange={setLeague} />
        <SlotsEditor league={league} onChange={setLeague} />
        <KeepersTradesEditor league={league} onChange={setLeague} />

        {errors.length > 0 && (
          <div className="callout error" role="alert">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="row" style={{ marginTop: 8 }}>
          <button type="button" className="primary" data-testid="setup-create" disabled={busy || !selectedSnapshot} onClick={() => void create()}>
            Create session and open draft
          </button>
          {selectedSnapshot?.is_demo && <span className="badge loud">DEMO DATA — synthetic players</span>}
          {!confirmFormat && <span className="muted">Format not confirmed: the draft screen will keep warning.</span>}
        </div>
      </section>
      </div>
    </>
  )
}
