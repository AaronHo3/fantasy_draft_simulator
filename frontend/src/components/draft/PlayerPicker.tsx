import { useEffect, useMemo, useReducer, useRef, useState, type KeyboardEvent } from 'react'
import { api } from '../../api/client'
import type { PlayerView } from '../../api/types'
import { managerName, pickLookup } from '../../lib/draftState'
import { fmtNum, PRIMITIVE_POSITIONS, positionsText } from '../../lib/format'
import { initialPickerState, pickerReducer } from '../../lib/keyboard'
import { useDraftStore } from '../../store/draftStore'
import { Icon } from '../ui/Icon'

const SEARCH_LIMIT = 60
const SEARCH_DEBOUNCE_MS = 150
type Availability = 'available' | 'drafted' | 'all'

function isTypingTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable
}

/** Find a player, record who drafted them. Enter selects, Enter again records; Esc backs out. */
export function PlayerPicker() {
  const sessionId = useDraftStore((s) => s.sessionId)
  const snapshotId = useDraftStore((s) => s.snapshotId)
  const state = useDraftStore((s) => s.state)
  const pendingCommit = useDraftStore((s) => s.pendingCommit)
  const commitPick = useDraftStore((s) => s.commitPick)
  const openDrawer = useDraftStore((s) => s.openDrawer)
  const previewPlayerId = useDraftStore((s) => s.previewPlayerId)
  const setPreview = useDraftStore((s) => s.setPreview)
  const [query, setQuery] = useState('')
  const [positions, setPositions] = useState<Set<string>>(() => new Set())
  const [availability, setAvailability] = useState<Availability>('available')
  const [results, setResults] = useState<PlayerView[]>([])
  const [loading, setLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [picker, dispatch] = useReducer(pickerReducer, initialPickerState)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const draftRevision = state?.draft_revision ?? -1
  const picks = useMemo(() => (state ? pickLookup(state) : new Map()), [state])

  useEffect(() => {
    if (!snapshotId) return
    let cancelled = false
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const r = await api.players(snapshotId, { q: query.trim() || undefined, limit: SEARCH_LIMIT, sessionId })
        if (!cancelled) {
          setResults(r)
          setSearchError(null)
        }
      } catch (e) {
        if (!cancelled) setSearchError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [query, snapshotId, sessionId, draftRevision])

  const filtered = useMemo(
    () =>
      results.filter((p) => {
        const drafted = picks.has(p.player_id)
        if (availability === 'available' && drafted) return false
        if (availability === 'drafted' && !drafted) return false
        if (positions.size > 0 && !p.eligible_positions.some((x) => positions.has(x))) return false
        return true
      }),
    [results, picks, availability, positions],
  )

  useEffect(() => {
    dispatch({ type: 'rows', rows: filtered.map((p) => ({ id: p.player_id, disabled: picks.has(p.player_id) })) })
  }, [filtered, picks])

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === '/' && !isTypingTarget(e.target) && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (picker.cursor < 0) return
    const el = listRef.current?.children[picker.cursor]
    if (el instanceof HTMLElement) el.scrollIntoView({ block: 'nearest' })
  }, [picker.cursor])

  const onClock = state?.on_clock_manager_id ?? null
  const byId = useMemo(() => new Map(filtered.map((p) => [p.player_id, p])), [filtered])
  const selected = picker.selectedId ? byId.get(picker.selectedId) ?? null : null

  const confirm = async () => {
    if (!picker.selectedId || !picker.managerId) return
    dispatch({ type: 'committed' })
    setQuery('')
    await commitPick(picker.selectedId, picker.managerId)
    inputRef.current?.focus()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      dispatch({ type: 'move', delta: 1 })
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      dispatch({ type: 'move', delta: -1 })
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (pendingCommit) return
      if (picker.stage === 'confirm') void confirm()
      else dispatch({ type: 'enter', defaultManagerId: onClock })
    } else if (e.key === 'Escape') {
      if (picker.stage === 'confirm') dispatch({ type: 'escape' })
      else if (query) setQuery('')
      else inputRef.current?.blur()
    }
  }

  const togglePos = (p: string) =>
    setPositions((prev) => {
      const next = new Set(prev)
      if (next.has(p)) next.delete(p)
      else next.add(p)
      return next
    })

  const uid = state?.league.user_manager_id ?? null
  const targetIsMe = picker.managerId !== null && picker.managerId === uid
  const mismatch = picker.managerId !== null && picker.managerId !== onClock

  return (
    <section className="panel" aria-labelledby="picker-h">
      <div className="panel-head">
        <h3 id="picker-h">Find player</h3>
        <span className="muted small-text">
          <span className="kbd">/</span> search · <span className="kbd">↑↓</span> · <span className="kbd">Enter</span> select, again to record · <span className="kbd">Esc</span>
        </span>
      </div>
      <div className="search-field">
        <Icon name="search" size={15} />
        <input
        ref={inputRef}
        type="search"
        data-testid="picker-search"
        aria-label="Search players by name, alias or team"
        placeholder="Name or team code…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={filtered.length > 0}
        aria-controls="picker-results"
        aria-activedescendant={picker.cursor >= 0 ? `picker-opt-${picker.cursor}` : undefined}
        autoComplete="off"
      />
      </div>
      <div className="picker-filters">
        <div className="chips" role="group" aria-label="Position filter">
          {PRIMITIVE_POSITIONS.map((p) => (
            <button type="button" key={p} aria-pressed={positions.has(p)} onClick={() => togglePos(p)}>
              {p}
            </button>
          ))}
        </div>
        <select aria-label="Availability" value={availability} onChange={(e) => setAvailability(e.target.value as Availability)} data-testid="picker-availability">
          <option value="available">available</option>
          <option value="drafted">drafted</option>
          <option value="all">everyone</option>
        </select>
        {(positions.size > 0 || availability !== 'available') && (
          <button type="button" className="small ghost" onClick={() => { setPositions(new Set()); setAvailability('available') }}>
            clear filters
          </button>
        )}
      </div>
      {picker.stage === 'confirm' && selected && state && (
        <div className="assign-bar" data-testid="confirm-pick-dialog" role="group" aria-label="Record pick">
          <div className="who">
            <span data-testid="confirm-pick-player" data-player-id={selected.player_id}>
              {selected.name}
            </span>{' '}
            <span className="meta">
              {selected.team ?? '—'} · {positionsText(selected.eligible_positions)} · ADP {fmtNum(selected.adp, 1)} · pick #{state.current_pick?.overall ?? '—'}
            </span>
          </div>
          <div className="controls">
            <label htmlFor="confirm-manager">Drafted by</label>
            <select id="confirm-manager" data-testid="confirm-pick-manager" value={picker.managerId ?? ''} onChange={(e) => dispatch({ type: 'manager', managerId: e.target.value })}>
              {state.league.managers.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                  {m.id === onClock ? ' (on the clock)' : ''}
                  {m.id === uid ? ' (me)' : ''}
                </option>
              ))}
            </select>
            <button type="button" className="primary" data-testid="confirm-pick-submit" disabled={pendingCommit !== null || mismatch} onClick={() => void confirm()}>
              {targetIsMe ? 'Draft to my team' : `Record for ${managerName(state, picker.managerId)}`} <span className="kbd" style={{ background: 'transparent', borderColor: 'rgb(255 255 255 / 0.5)' }}>↵</span>
            </button>
            <button type="button" className="ghost" onClick={() => { dispatch({ type: 'escape' }); inputRef.current?.focus() }}>
              Cancel
            </button>
          </div>
          {mismatch && (
            <p className="callout warn small-text" role="alert" style={{ margin: 0 }}>
              {managerName(state, onClock)} is on the clock; picks are recorded in draft order. If the order is wrong, fix it in Setup.
            </p>
          )}
        </div>
      )}
      {searchError && (
        <p className="callout error" role="alert">
          Search failed: {searchError}
        </p>
      )}
      <ul className="picker-results" id="picker-results" role="listbox" aria-label="Players" ref={listRef} data-testid="picker-results" aria-busy={loading}>
        {filtered.map((p, i) => {
          const rec = picks.get(p.player_id)
          const drafted = rec !== undefined
          const missingProjection = p.projection_source === 'prior'
          return (
            <li
              key={p.player_id}
              id={`picker-opt-${i}`}
              role="option"
              aria-selected={picker.cursor === i}
              aria-disabled={drafted}
              className={drafted ? 'drafted' : undefined}
              data-testid="picker-row"
              data-player-id={p.player_id}
              data-drafted={drafted ? 'true' : 'false'}
              onMouseEnter={() => dispatch({ type: 'hover', index: i })}
              onClick={() => {
                if (drafted) {
                  openDrawer(p.player_id)
                  return
                }
                if (!pendingCommit) dispatch({ type: 'select', id: p.player_id, defaultManagerId: onClock })
              }}
            >
              <span>
                <b data-testid="picker-name">{p.name}</b> <span className="muted">{p.team ?? '—'}</span>
                {p.eligible_positions.map((x) => (
                  <span key={x} className="pos-chip">
                    {x}
                  </span>
                ))}
                {!p.eligibility_verified && <span className="badge warn"> unverified</span>}
              </span>
              <span className="meta">
                ADP {fmtNum(p.adp, 1)}
                {!drafted && (
                  <>
                    {' '}
                    <button
                      type="button"
                      className="small ghost"
                      aria-pressed={previewPlayerId === p.player_id}
                      title="Preview how this player changes my roster and categories"
                      onClick={(e) => {
                        e.stopPropagation()
                        setPreview(previewPlayerId === p.player_id ? null : p.player_id)
                      }}
                    >
                      {previewPlayerId === p.player_id ? 'previewing' : 'preview'}
                    </button>
                  </>
                )}
              </span>
              {drafted && state && (
                <span className="sub">
                  drafted by {managerName(state, rec.manager_id)} at #{rec.overall}
                </span>
              )}
              {!drafted && (p.injury_status && p.injury_status !== 'ACTIVE' || missingProjection) && (
                <span className="sub">
                  {p.injury_status && p.injury_status !== 'ACTIVE' ? `status ${p.injury_status}` : ''}
                  {p.injury_status && p.injury_status !== 'ACTIVE' && missingProjection ? ' · ' : ''}
                  {missingProjection ? 'no projection: prior only' : ''}
                </span>
              )}
            </li>
          )
        })}
        {!loading && filtered.length === 0 && (
          <li className="muted" style={{ cursor: 'default', display: 'block' }}>
            {results.length === 0 ? 'No players match that search.' : 'No players match the filters.'}
          </li>
        )}
      </ul>
    </section>
  )
}
