import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type ApiClient } from '../api/client'
import type { SeasonOverview, SyncResult } from '../api/types'
import { memoryStorage } from '../lib/storage'
import { makeState } from '../test/fixtures'
import { AUTO_REFRESH_KEY, createSeasonStore } from './seasonStore'

function makeOverview(over: Partial<SeasonOverview> = {}): SeasonOverview {
  return {
    ids: { draft_revision: 3, strategy_revision: 0, league_revision: 1, last_seq: 3, snapshot_id: 'demo', projection_version: 'v', seed: 1 },
    linked: true,
    league_name: 'Fake League',
    synced_at: '2026-10-19T04:00:00+00:00',
    summary: 'ESPN sync: 0 adds, 0 drops across 0 teams; 0 unknown players',
    warnings: [],
    current_period: 1,
    league_categories: [],
    manager_names: { m01: 'Me', m02: 'Them' },
    power: [],
    movement: {},
    matchups: [],
    user_matchup: null,
    ...over,
  }
}

function makeSync(over: Partial<SyncResult> = {}): SyncResult {
  return {
    ids: { draft_revision: 4, strategy_revision: 0, league_revision: 1, last_seq: 4, snapshot_id: 'demo', projection_version: 'v', seed: 1 },
    fetched_at: '2026-10-19T05:00:00+00:00',
    summary: 'ESPN sync: 1 adds, 1 drops across 1 teams; 0 unknown players',
    changes: [],
    warnings: [],
    unknown_players: [],
    state: makeState(),
    ...over,
  }
}

function fakeApi(overrides: Partial<ApiClient> = {}): ApiClient {
  const notImpl = () => Promise.reject(new Error('not implemented in fake'))
  return new Proxy({ ...overrides } as ApiClient, {
    get: (target, prop: keyof ApiClient) => target[prop] ?? notImpl,
  })
}

describe('season store', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('sync updates lastSync, reloads the overview and the draft session', async () => {
    let overviewCalls = 0
    const reloaded: string[] = []
    const api = fakeApi({
      seasonOverview: () => {
        overviewCalls += 1
        return Promise.resolve(makeOverview({ synced_at: overviewCalls === 1 ? '2026-10-19T04:00:00+00:00' : '2026-10-19T05:00:00+00:00' }))
      },
      espnSync: () => Promise.resolve(makeSync()),
    })
    const store = createSeasonStore({ api, storage: memoryStorage(), reloadSession: async (id) => void reloaded.push(id) })
    await store.getState().loadOverview('sess')
    expect(store.getState().overview?.synced_at).toBe('2026-10-19T04:00:00+00:00')
    const ok = await store.getState().sync('sess', 3)
    expect(ok).toBe(true)
    expect(store.getState().syncStatus).toBe('idle')
    expect(store.getState().lastSync?.summary).toContain('1 adds')
    expect(store.getState().overview?.synced_at).toBe('2026-10-19T05:00:00+00:00')
    expect(reloaded).toEqual(['sess'])
    expect(overviewCalls).toBe(2)
  })

  it('auto-refresh syncs on the interval, persists the choice, and stops at 0', async () => {
    let syncs = 0
    const storage = memoryStorage()
    const api = fakeApi({
      seasonOverview: () => Promise.resolve(makeOverview()),
      espnSync: () => {
        syncs += 1
        return Promise.resolve(makeSync())
      },
    })
    const store = createSeasonStore({ api, storage, reloadSession: async () => {} })
    await store.getState().loadOverview('sess')
    store.getState().setAutoRefresh(15)
    expect(storage.get(AUTO_REFRESH_KEY)).toBe('15')
    await vi.advanceTimersByTimeAsync(15 * 60_000)
    expect(syncs).toBe(1)
    await vi.advanceTimersByTimeAsync(15 * 60_000)
    expect(syncs).toBe(2)
    store.getState().setAutoRefresh(0)
    await vi.advanceTimersByTimeAsync(60 * 60_000)
    expect(syncs).toBe(2)
    expect(storage.get(AUTO_REFRESH_KEY)).toBe('0')
    // a stored preference is restored on creation
    const again = createSeasonStore({ api, storage, reloadSession: async () => {} })
    expect(again.getState().autoRefreshMin).toBe(0)
    storage.set(AUTO_REFRESH_KEY, '60')
    expect(createSeasonStore({ api, storage, reloadSession: async () => {} }).getState().autoRefreshMin).toBe(60)
  })

  it('a stored auto-refresh setting is armed again when the screen loads after a reload', async () => {
    let syncs = 0
    const storage = memoryStorage()
    storage.set(AUTO_REFRESH_KEY, '15')
    const api = fakeApi({
      seasonOverview: () => Promise.resolve(makeOverview()),
      espnSync: () => {
        syncs += 1
        return Promise.resolve(makeSync())
      },
    })
    const store = createSeasonStore({ api, storage, reloadSession: async () => {} })
    expect(store.getState().autoRefreshMin).toBe(15)
    await store.getState().loadOverview('sess')
    store.getState().start()
    await vi.advanceTimersByTimeAsync(15 * 60_000)
    expect(syncs).toBe(1)
    store.getState().stop()
    await vi.advanceTimersByTimeAsync(15 * 60_000)
    expect(syncs).toBe(1)
    store.getState().start()
    await vi.advanceTimersByTimeAsync(15 * 60_000)
    expect(syncs).toBe(2)
  })

  it('a revision conflict (another sync landed first) reloads quietly instead of showing an error', async () => {
    let overviewCalls = 0
    const api = fakeApi({
      seasonOverview: () => {
        overviewCalls += 1
        return Promise.resolve(makeOverview())
      },
      espnSync: () => Promise.reject(new ApiError(409, 'revision_conflict', 'stale revision')),
    })
    const store = createSeasonStore({ api, storage: memoryStorage(), reloadSession: async () => {} })
    await store.getState().loadOverview('sess')
    const ok = await store.getState().sync('sess', 3)
    expect(ok).toBe(true)
    expect(store.getState().syncStatus).toBe('idle')
    expect(store.getState().syncError).toBeNull()
    expect(overviewCalls).toBe(2)
  })

  it('a failed sync keeps the previous overview and reports the server message', async () => {
    const api = fakeApi({
      seasonOverview: () => Promise.resolve(makeOverview()),
      espnSync: () => Promise.reject(new ApiError(409, 'league_private', 'ESPN league 1 is private.')),
    })
    const store = createSeasonStore({ api, storage: memoryStorage(), reloadSession: async () => {} })
    await store.getState().loadOverview('sess')
    const ok = await store.getState().sync('sess')
    expect(ok).toBe(false)
    expect(store.getState().syncStatus).toBe('error')
    expect(store.getState().syncError).toContain('private')
    expect(store.getState().overview?.league_name).toBe('Fake League')
  })

  it('loads free agents and results with their own status flags', async () => {
    const api = fakeApi({
      seasonFreeAgents: (_id, opts) => Promise.resolve({ ids: makeOverview().ids, items: [], synced_at: null, ...(opts.q ? {} : {}) }),
      seasonResults: (_id, period) => Promise.resolve({ ids: makeOverview().ids, period, results: [], projected: [] }),
    })
    const store = createSeasonStore({ api, storage: memoryStorage(), reloadSession: async () => {} })
    await store.getState().loadFreeAgents('sess', { q: 'x' })
    expect(store.getState().faStatus).toBe('ready')
    await store.getState().loadResults('sess', 2)
    expect(store.getState().resultsStatus).toBe('ready')
    expect(store.getState().results?.period).toBe(2)
  })
})
