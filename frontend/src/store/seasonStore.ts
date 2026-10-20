// Season screen state: ESPN sync, overview (power + matchups), free agents and results.
// Sync is the only action that reaches ESPN; everything else reads the backend's stored state.
import { create } from 'zustand'
import { ApiError, api as defaultApi, type ApiClient } from '../api/client'
import type { FreeAgentsResponse, PredictionsResponse, SeasonOverview, SyncResult, WeekResultsResponse } from '../api/types'
import { browserStorage, type KeyValueStorage } from '../lib/storage'
import { useDraftStore } from './draftStore'

export const AUTO_REFRESH_KEY = 'copilot.season.autoRefresh'
export type AutoRefreshMinutes = 0 | 15 | 60
export const AUTO_REFRESH_OPTIONS: AutoRefreshMinutes[] = [0, 15, 60]
type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface SeasonDeps {
  api: ApiClient
  storage: KeyValueStorage
  reloadSession: (sessionId: string) => Promise<void>
}

export interface FreeAgentQuery {
  limit?: number
  position?: string | null
  q?: string | null
}

export interface SeasonStore {
  sessionId: string | null
  overview: SeasonOverview | null
  overviewStatus: LoadStatus
  overviewError: string | null
  period: number | null
  freeAgents: FreeAgentsResponse | null
  faStatus: LoadStatus
  faError: string | null
  results: WeekResultsResponse | null
  resultsStatus: LoadStatus
  resultsError: string | null
  predictions: PredictionsResponse | null
  predictionsStatus: LoadStatus
  predictionsError: string | null
  syncStatus: 'idle' | 'syncing' | 'error'
  syncError: string | null
  lastSync: SyncResult | null
  autoRefreshMin: AutoRefreshMinutes

  loadOverview(sessionId: string, period?: number | null): Promise<void>
  sync(sessionId: string, expectedRevision?: number | null): Promise<boolean>
  loadFreeAgents(sessionId: string, query?: FreeAgentQuery): Promise<void>
  loadResults(sessionId: string, period: number): Promise<void>
  loadPredictions(sessionId: string): Promise<void>
  setPeriod(period: number | null): void
  setAutoRefresh(minutes: AutoRefreshMinutes): void
  start(): void
  stop(): void
}

const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e))

function readAutoRefresh(storage: KeyValueStorage): AutoRefreshMinutes {
  const raw = Number(storage.get(AUTO_REFRESH_KEY) ?? '0')
  return (AUTO_REFRESH_OPTIONS as number[]).includes(raw) ? (raw as AutoRefreshMinutes) : 0
}

export function createSeasonStore(overrides: Partial<SeasonDeps> = {}) {
  const deps: SeasonDeps = {
    api: defaultApi,
    storage: browserStorage,
    reloadSession: (id) => useDraftStore.getState().loadSession(id),
    ...overrides,
  }
  const { api, storage } = deps
  let timer: ReturnType<typeof setInterval> | null = null
  let overviewSeq = 0

  return create<SeasonStore>()((set, get) => {
    const clearTimer = () => {
      if (timer) clearInterval(timer)
      timer = null
    }

    const armTimer = () => {
      clearTimer()
      const { autoRefreshMin } = get()
      if (autoRefreshMin > 0) {
        timer = setInterval(() => {
          const { sessionId, syncStatus } = get()
          if (sessionId && syncStatus !== 'syncing') void get().sync(sessionId)
        }, autoRefreshMin * 60_000)
      }
    }

    return {
      sessionId: null,
      overview: null,
      overviewStatus: 'idle',
      overviewError: null,
      period: null,
      freeAgents: null,
      faStatus: 'idle',
      faError: null,
      results: null,
      resultsStatus: 'idle',
      resultsError: null,
      predictions: null,
      predictionsStatus: 'idle',
      predictionsError: null,
      syncStatus: 'idle',
      syncError: null,
      lastSync: null,
      autoRefreshMin: readAutoRefresh(storage),

      async loadOverview(sessionId, period = get().period) {
        overviewSeq += 1
        const mySeq = overviewSeq
        set({ sessionId, overviewStatus: 'loading', overviewError: null })
        try {
          const overview = await api.seasonOverview(sessionId, { period })
          if (mySeq !== overviewSeq) return
          set({ overview, overviewStatus: 'ready', period: overview.current_period }) // the period actually shown
        } catch (e) {
          if (mySeq !== overviewSeq) return
          set({ overviewStatus: 'error', overviewError: errorText(e) })
        }
      },

      async sync(sessionId, expectedRevision = null) {
        set({ syncStatus: 'syncing', syncError: null })
        try {
          const result = await api.espnSync(sessionId, expectedRevision)
          set({ lastSync: result, syncStatus: 'idle' })
          await deps.reloadSession(sessionId)
          await get().loadOverview(sessionId)
          return true
        } catch (e) {
          if (e instanceof ApiError && e.code === 'revision_conflict') {
            // another sync (other tab, CLI, auto-refresh) landed first: its result is already stored
            set({ syncStatus: 'idle', syncError: null })
            await deps.reloadSession(sessionId)
            await get().loadOverview(sessionId)
            return true
          }
          set({ syncStatus: 'error', syncError: errorText(e) })
          return false
        }
      },

      async loadFreeAgents(sessionId, query = {}) {
        set({ faStatus: 'loading', faError: null })
        try {
          const freeAgents = await api.seasonFreeAgents(sessionId, query)
          set({ freeAgents, faStatus: 'ready' })
        } catch (e) {
          set({ faStatus: 'error', faError: errorText(e) })
        }
      },

      async loadResults(sessionId, period) {
        set({ resultsStatus: 'loading', resultsError: null })
        try {
          const results = await api.seasonResults(sessionId, period)
          set({ results, resultsStatus: 'ready' })
        } catch (e) {
          set({ resultsStatus: 'error', resultsError: errorText(e) })
        }
      },

      async loadPredictions(sessionId) {
        set({ predictionsStatus: 'loading', predictionsError: null })
        try {
          const predictions = await api.seasonPredictions(sessionId)
          set({ predictions, predictionsStatus: 'ready' })
        } catch (e) {
          set({ predictionsStatus: 'error', predictionsError: errorText(e) })
        }
      },

      setPeriod(period) {
        set({ period })
      },

      setAutoRefresh(minutes) {
        storage.set(AUTO_REFRESH_KEY, String(minutes))
        set({ autoRefreshMin: minutes })
        armTimer()
      },

      start() {
        armTimer()
      },

      stop() {
        clearTimer()
      },
    }
  })
}

export const useSeasonStore = createSeasonStore()
