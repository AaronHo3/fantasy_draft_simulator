// Session state, recommendations, refine jobs and pending commits. Created through a factory so tests
// can inject a fake API client, a memory storage and zero debounce delays.
import { create } from 'zustand'
import { ApiError, api as defaultApi, type ApiClient } from '../api/client'
import type {
  CandidateView,
  CompareResponse,
  DraftStateView,
  EventType,
  LeagueConfig,
  PlayerView,
  RecommendationResponse,
  RefinementResponse,
  ResponseIds,
  SnapshotMeta,
  Strategy,
} from '../api/types'
import { applyLocalPick, LocalCommitError, type LocalPick } from '../lib/draftState'
import { newIdempotencyKey } from '../lib/format'
import { coerceIds, idsMatch } from '../lib/revision'
import { browserStorage, pendingKey, readJson, SESSION_KEY, type KeyValueStorage } from '../lib/storage'

export interface PendingCommit {
  key: string
  sessionId: string
  payload: LocalPick
  expected_revision: number
}

export type NoticeKind = 'info' | 'warn' | 'error'
export interface Notice {
  id: number
  kind: NoticeKind
  text: string
}

export type SaveStatus = 'saved' | 'saving' | 'offline' | 'error'
export type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'
export type RefineStatus = 'queued' | 'running' | 'done' | 'failed' | 'timeout' | 'discarded'

export interface RefineJob {
  jobId: string
  ids: ResponseIds | null
  status: RefineStatus
  startedAt: number
  elapsedMs: number | null
  error: string | null
}

export interface StoreDeps {
  api: ApiClient
  storage: KeyValueStorage
  fastDelayMs: number
  refineDelayMs: number
  pollMs: number
  pollCapMs: number
  retryMs: number
  recLimit: number
  refineLimit: number
}

export const defaultDeps: StoreDeps = {
  api: defaultApi,
  storage: browserStorage,
  fastDelayMs: 150,
  refineDelayMs: 400,
  pollMs: 400,
  pollCapMs: 20_000,
  retryMs: 2_000,
  recLimit: 25,
  refineLimit: 8,
}

export interface DraftStore {
  sessionId: string | null
  sessionName: string | null
  snapshotId: string | null
  state: DraftStateView | null
  stateStatus: LoadStatus
  stateError: string | null
  saveStatus: SaveStatus
  pendingCommit: PendingCommit | null
  notices: Notice[]
  rec: RecommendationResponse | null
  recStatus: 'idle' | 'updating' | 'ready' | 'error'
  recError: string | null
  previewPlayerId: string | null
  previewCandidate: CandidateView | null
  refineJob: RefineJob | null
  refineResult: RefinementResponse | null
  refineUnavailable: boolean
  players: Record<string, PlayerView>
  playersStatus: LoadStatus
  snapshot: SnapshotMeta | null
  drawerPlayerId: string | null
  compareIds: string[]
  compareResult: CompareResponse | null
  compareStatus: LoadStatus
  compareError: string | null
  compareOpen: boolean

  loadSession(id: string): Promise<void>
  clearSession(): void
  refreshState(): Promise<void>
  commitPick(playerId: string, managerId: string): Promise<void>
  retryPending(): Promise<void>
  undoLastPick(): Promise<boolean>
  correctPick(overall: number, playerId: string): Promise<boolean>
  sendEvent(type: EventType, payload: Record<string, unknown>): Promise<boolean>
  setStrategy(strategy: Strategy): Promise<boolean>
  confirmFormat(): Promise<boolean>
  updateLeague(league: LeagueConfig): Promise<boolean>
  setPreview(playerId: string | null, candidate?: CandidateView | null): void
  requestRecommendation(): void
  openDrawer(playerId: string | null): void
  toggleCompare(playerId: string): void
  clearCompare(): void
  runCompare(): Promise<void>
  closeCompare(): void
  notify(kind: NoticeKind, text: string): void
  dismissNotice(id: number): void
}

const MAX_NOTICES = 5

export function createDraftStore(overrides: Partial<StoreDeps> = {}) {
  const deps: StoreDeps = { ...defaultDeps, ...overrides }
  const { api, storage } = deps
  let fastTimer: ReturnType<typeof setTimeout> | null = null
  let refineTimer: ReturnType<typeof setTimeout> | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let fastSeq = 0
  let refineSeq = 0
  let noticeSeq = 0
  // In-memory only: the state to restore when the server rejects an optimistic pick.
  let rollbackState: DraftStateView | null = null

  const clearTimer = (t: ReturnType<typeof setTimeout> | null) => {
    if (t) clearTimeout(t)
  }

  return create<DraftStore>()((set, get) => {
    const notify = (kind: NoticeKind, text: string) => {
      noticeSeq += 1
      set((s) => ({ notices: [...s.notices.slice(-(MAX_NOTICES - 1)), { id: noticeSeq, kind, text }] }))
    }

    const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e))

    // --- recommendations ----------------------------------------------------------------------
    const runFast = async () => {
      const { sessionId, state, previewPlayerId } = get()
      if (!sessionId || !state) return
      fastSeq += 1
      const mySeq = fastSeq
      set({ recStatus: 'updating' })
      try {
        const res = await api.recommendFast(sessionId, {
          limit: deps.recLimit,
          include_deltas: Math.min(deps.recLimit, 50),
          preview_player_id: previewPlayerId,
        })
        if (mySeq !== fastSeq) return // a newer request is in flight
        const cur = get().state
        if (!idsMatch(res.ids, cur)) return // stale: state moved on while the server computed; drop it
        set({ rec: res, recStatus: 'ready', recError: null })
      } catch (e) {
        if (mySeq !== fastSeq) return
        set({ recStatus: 'error', recError: errorText(e) })
      }
    }

    const stopPolling = () => {
      clearTimer(pollTimer)
      pollTimer = null
    }

    const pollJob = (jobId: string, mySeq: number) => {
      const tick = async () => {
        if (mySeq !== refineSeq) return
        const { sessionId, refineJob } = get()
        if (!sessionId || !refineJob || refineJob.jobId !== jobId) return
        if (Date.now() - refineJob.startedAt > deps.pollCapMs) {
          set({ refineJob: { ...refineJob, status: 'timeout' } })
          return
        }
        try {
          const job = await api.job(jobId, sessionId)
          if (mySeq !== refineSeq) return
          const cur = get()
          if (!cur.refineJob || cur.refineJob.jobId !== jobId) return
          if (job.status === 'queued' || job.status === 'running') {
            set({ refineJob: { ...cur.refineJob, status: job.status } })
            pollTimer = setTimeout(tick, deps.pollMs)
            return
          }
          if (job.status === 'failed') {
            set({ refineJob: { ...cur.refineJob, status: 'failed', error: job.error ?? 'refine failed', elapsedMs: job.elapsed_ms ?? null } })
            return
          }
          const result = job.result ?? null
          const jobIds = coerceIds(job.ids)
          if (job.stale || !result || !idsMatch(result.ids, cur.state) || !idsMatch(jobIds, cur.state)) {
            set({ refineJob: { ...cur.refineJob, status: 'discarded', elapsedMs: job.elapsed_ms ?? null } })
            return
          }
          set({ refineResult: result, refineJob: { ...cur.refineJob, status: 'done', elapsedMs: job.elapsed_ms ?? null } })
        } catch (e) {
          if (mySeq !== refineSeq) return
          const cur = get().refineJob
          if (cur) set({ refineJob: { ...cur, status: 'failed', error: errorText(e) } })
        }
      }
      pollTimer = setTimeout(tick, deps.pollMs)
    }

    const runRefine = async () => {
      const { sessionId, state, refineUnavailable } = get()
      if (!sessionId || !state || refineUnavailable || state.is_complete) return
      refineSeq += 1
      const mySeq = refineSeq
      stopPolling()
      try {
        const accepted = await api.refine(sessionId, { limit: deps.refineLimit })
        if (mySeq !== refineSeq) return
        if (!idsMatch(accepted.ids, get().state)) return
        set({ refineJob: { jobId: accepted.job_id, ids: accepted.ids, status: 'queued', startedAt: Date.now(), elapsedMs: null, error: null } })
        pollJob(accepted.job_id, mySeq)
      } catch (e) {
        if (mySeq !== refineSeq) return
        if (e instanceof ApiError && e.status === 501) {
          set({ refineUnavailable: true, refineJob: null })
          return
        }
        set({ refineJob: { jobId: '', ids: null, status: 'failed', startedAt: Date.now(), elapsedMs: null, error: errorText(e) } })
      }
    }

    const scheduleRecommendations = () => {
      clearTimer(fastTimer)
      clearTimer(refineTimer)
      stopPolling()
      refineSeq += 1 // invalidate any in-flight refine
      const { state, pendingCommit } = get()
      if (!state) return
      // While an optimistic pick is unsaved the server does not know our revision yet; wait for it.
      if (pendingCommit) {
        set({ recStatus: 'updating' })
        return
      }
      set({ recStatus: 'updating' })
      fastTimer = setTimeout(() => void runFast(), deps.fastDelayMs)
      refineTimer = setTimeout(() => void runRefine(), deps.refineDelayMs)
    }

    const applyServerState = (state: DraftStateView) => {
      set({ state, stateStatus: 'ready', stateError: null })
      scheduleRecommendations()
    }

    // --- pending commit -----------------------------------------------------------------------
    const persistPending = (p: PendingCommit | null, sessionId: string) => {
      if (p) storage.set(pendingKey(sessionId), JSON.stringify(p))
      else storage.remove(pendingKey(sessionId))
    }

    const sendPending = async (): Promise<void> => {
      const p = get().pendingCommit
      if (!p) return
      clearTimer(retryTimer)
      set({ saveStatus: 'saving' })
      try {
        const res = await api.appendEvent(p.sessionId, {
          type: 'pick_committed',
          payload: { ...p.payload },
          idempotency_key: p.key,
          expected_revision: p.expected_revision,
          source: 'manual',
        })
        if (get().pendingCommit?.key !== p.key) return
        rollbackState = null
        persistPending(null, p.sessionId)
        set({ pendingCommit: null, saveStatus: 'saved' })
        applyServerState(res.state)
        if (res.deduplicated) notify('info', 'That pick had already been saved; state synced from the server.')
      } catch (e) {
        if (get().pendingCommit?.key !== p.key) return
        if (e instanceof ApiError && e.isNetwork) {
          set({ saveStatus: 'offline' })
          retryTimer = setTimeout(() => void sendPending(), deps.retryMs)
          return
        }
        persistPending(null, p.sessionId)
        if (e instanceof ApiError && e.status === 409) {
          rollbackState = null
          set({ pendingCommit: null, saveStatus: 'saved' })
          notify('warn', `Revision conflict (${e.message}); state refreshed from the server. Check whether your pick was recorded.`)
          await get().refreshState()
          return
        }
        if (e instanceof ApiError && e.status === 422) {
          const prev = rollbackState
          rollbackState = null
          set({ pendingCommit: null, saveStatus: 'saved' })
          notify('error', `Pick rejected: ${e.message}`)
          if (prev) applyServerState(prev)
          else await get().refreshState()
          return
        }
        rollbackState = null
        set({ pendingCommit: null, saveStatus: 'error' })
        notify('error', `Could not save pick: ${errorText(e)}`)
        await get().refreshState()
      }
    }

    return {
      sessionId: null,
      sessionName: null,
      snapshotId: null,
      state: null,
      stateStatus: 'idle',
      stateError: null,
      saveStatus: 'saved',
      pendingCommit: null,
      notices: [],
      rec: null,
      recStatus: 'idle',
      recError: null,
      previewPlayerId: null,
      previewCandidate: null,
      refineJob: null,
      refineResult: null,
      refineUnavailable: false,
      players: {},
      playersStatus: 'idle',
      snapshot: null,
      drawerPlayerId: null,
      compareIds: [],
      compareResult: null,
      compareStatus: 'idle',
      compareError: null,
      compareOpen: false,

      notify,
      dismissNotice: (id) => set((s) => ({ notices: s.notices.filter((n) => n.id !== id) })),

      async loadSession(id) {
        clearTimer(fastTimer)
        clearTimer(refineTimer)
        clearTimer(retryTimer)
        stopPolling()
        rollbackState = null
        set({
          sessionId: id,
          stateStatus: 'loading',
          stateError: null,
          state: null,
          rec: null,
          recStatus: 'idle',
          refineJob: null,
          refineResult: null,
          refineUnavailable: false,
          previewPlayerId: null,
          previewCandidate: null,
          pendingCommit: null,
          compareIds: [],
          compareResult: null,
          compareOpen: false,
          drawerPlayerId: null,
        })
        storage.set(SESSION_KEY, id)
        try {
          const detail = await api.getSession(id)
          if (get().sessionId !== id) return
          set({ sessionName: detail.meta.name, snapshotId: detail.meta.snapshot_id ?? null })
          const pending = readJson<PendingCommit>(storage, pendingKey(id))
          if (pending && pending.sessionId === id) {
            // A pick that never reached the server: keep it visible as unsaved and retry with the same key.
            set({ pendingCommit: pending, saveStatus: 'offline' })
          }
          applyServerState(detail.state)
          const snapId = detail.meta.snapshot_id
          if (snapId) {
            set({ playersStatus: 'loading' })
            void Promise.all([api.players(snapId, { limit: 2000 }), api.snapshots()])
              .then(([players, snaps]) => {
                if (get().sessionId !== id) return
                const index: Record<string, PlayerView> = {}
                for (const p of players) index[p.player_id] = p
                set({ players: index, playersStatus: 'ready', snapshot: snaps.find((s) => s.snapshot_id === snapId) ?? null })
              })
              .catch((e: unknown) => {
                if (get().sessionId !== id) return
                set({ playersStatus: 'error' })
                notify('warn', `Could not load the player index: ${errorText(e)}`)
              })
          }
          if (get().pendingCommit) void sendPending()
        } catch (e) {
          if (get().sessionId !== id) return
          set({ stateStatus: 'error', stateError: errorText(e) })
        }
      },

      clearSession() {
        clearTimer(fastTimer)
        clearTimer(refineTimer)
        clearTimer(retryTimer)
        stopPolling()
        storage.remove(SESSION_KEY)
        set({ sessionId: null, sessionName: null, snapshotId: null, state: null, stateStatus: 'idle', rec: null, recStatus: 'idle', refineJob: null, refineResult: null, pendingCommit: null })
      },

      async refreshState() {
        const { sessionId } = get()
        if (!sessionId) return
        try {
          const st = await api.getState(sessionId)
          if (get().sessionId !== sessionId) return
          applyServerState(st)
        } catch (e) {
          set({ stateStatus: 'error', stateError: errorText(e) })
        }
      },

      async commitPick(playerId, managerId) {
        const { sessionId, state, pendingCommit } = get()
        if (!sessionId || !state) return
        if (pendingCommit) {
          notify('warn', 'A pick is still being saved; wait for it to land before entering another.')
          return
        }
        if (!state.current_pick) {
          notify('error', 'The draft is complete.')
          return
        }
        const payload: LocalPick = { player_id: playerId, overall: state.current_pick.overall, manager_id: managerId }
        let optimistic: DraftStateView
        try {
          optimistic = applyLocalPick(state, payload)
        } catch (e) {
          notify('error', e instanceof LocalCommitError ? e.message : errorText(e))
          return
        }
        const pending: PendingCommit = { key: newIdempotencyKey(), sessionId, payload, expected_revision: state.last_seq }
        rollbackState = state
        persistPending(pending, sessionId)
        set({ state: optimistic, pendingCommit: pending, saveStatus: 'saving', previewPlayerId: null, previewCandidate: null })
        scheduleRecommendations()
        await sendPending()
      },

      retryPending: () => sendPending(),

      async sendEvent(type, payload) {
        const { sessionId, state } = get()
        if (!sessionId || !state) return false
        set({ saveStatus: 'saving' })
        try {
          const res = await api.appendEvent(sessionId, {
            type,
            payload,
            idempotency_key: newIdempotencyKey(),
            expected_revision: state.last_seq,
            source: 'manual',
          })
          if (get().sessionId !== sessionId) return false
          set({ saveStatus: 'saved' })
          applyServerState(res.state)
          return true
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            set({ saveStatus: 'saved' })
            notify('warn', `Revision conflict (${e.message}); state refreshed from the server. Retry the change.`)
            await get().refreshState()
            return false
          }
          if (e instanceof ApiError && e.isNetwork) {
            set({ saveStatus: 'offline' })
            notify('error', 'Backend unreachable; the change was not saved.')
            return false
          }
          set({ saveStatus: 'error' })
          notify('error', `${type.replace('_', ' ')} rejected: ${errorText(e)}`)
          return false
        }
      },

      async undoLastPick() {
        return get().sendEvent('pick_undone', {})
      },

      async correctPick(overall, playerId) {
        return get().sendEvent('pick_corrected', { overall, player_id: playerId })
      },

      async setStrategy(strategy) {
        const { state } = get()
        if (!state) return false
        // Optimistic strategy so the panel feels immediate; the server state replaces it.
        set({ state: { ...state, strategy } })
        return get().sendEvent('strategy_changed', { strategy })
      },

      confirmFormat: () => get().sendEvent('format_confirmed', {}),

      updateLeague: (league) => get().sendEvent('league_updated', { league }),

      setPreview(playerId, candidate = null) {
        const id = playerId
        if (id === get().previewPlayerId) return
        set({ previewPlayerId: id, previewCandidate: candidate })
        clearTimer(fastTimer)
        set({ recStatus: 'updating' })
        fastTimer = setTimeout(() => void runFast(), deps.fastDelayMs)
      },

      requestRecommendation: () => scheduleRecommendations(),

      openDrawer: (playerId) => set({ drawerPlayerId: playerId }),

      toggleCompare(playerId) {
        set((s) => {
          if (s.compareIds.includes(playerId)) return { compareIds: s.compareIds.filter((x) => x !== playerId) }
          if (s.compareIds.length >= 3) return { compareIds: [...s.compareIds.slice(1), playerId] }
          return { compareIds: [...s.compareIds, playerId] }
        })
      },

      clearCompare: () => set({ compareIds: [], compareResult: null, compareOpen: false }),

      async runCompare() {
        const { sessionId, compareIds } = get()
        if (!sessionId || compareIds.length < 2) return
        set({ compareOpen: true, compareStatus: 'loading', compareError: null })
        try {
          const res = await api.compare(sessionId, compareIds)
          set({ compareResult: res, compareStatus: 'ready' })
        } catch (e) {
          set({ compareStatus: 'error', compareError: errorText(e) })
        }
      },

      closeCompare: () => set({ compareOpen: false }),
    }
  })
}

export type DraftStoreHook = ReturnType<typeof createDraftStore>
export const useDraftStore: DraftStoreHook = createDraftStore()

// --- selectors ------------------------------------------------------------------------------
export function selectRecCurrent(s: Pick<DraftStore, 'rec' | 'state' | 'pendingCommit'>): boolean {
  return s.rec !== null && s.state !== null && s.pendingCommit === null && idsMatch(s.rec.ids, s.state)
}

export function selectRefineCurrent(s: Pick<DraftStore, 'refineResult' | 'state' | 'pendingCommit'>): boolean {
  return s.refineResult !== null && s.state !== null && s.pendingCommit === null && idsMatch(s.refineResult.ids, s.state)
}

export interface TierInfo {
  tier: string
  computedMs: number | null
  label: string
}

export function selectTier(s: Pick<DraftStore, 'rec' | 'refineResult' | 'state' | 'pendingCommit' | 'refineJob' | 'refineUnavailable'>): TierInfo {
  if (selectRefineCurrent(s) && s.refineResult) {
    return { tier: s.refineResult.tier, computedMs: s.refineResult.computed_ms, label: `tier ${s.refineResult.tier} (refined)` }
  }
  if (selectRecCurrent(s) && s.rec) {
    const pending = s.refineJob && (s.refineJob.status === 'queued' || s.refineJob.status === 'running')
    const suffix = s.refineUnavailable ? ', refine unavailable' : pending ? ', refining…' : ''
    return { tier: s.rec.tier, computedMs: s.rec.computed_ms, label: `tier ${s.rec.tier}${suffix}` }
  }
  return { tier: '—', computedMs: null, label: 'updating…' }
}
