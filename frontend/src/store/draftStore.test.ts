import { describe, expect, it, vi } from 'vitest'
import { ApiError, type ApiClient } from '../api/client'
import type { DraftStateView, RecommendationResponse } from '../api/types'
import { applyLocalPick } from '../lib/draftState'
import { memoryStorage, pendingKey } from '../lib/storage'
import { makeRec, makeState } from '../test/fixtures'
import { createDraftStore, selectRecCurrent } from './draftStore'

const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms))

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function fakeApi(state: DraftStateView, overrides: Partial<ApiClient> = {}): ApiClient {
  const notImpl = () => Promise.reject(new Error('not implemented in fake'))
  return {
    health: notImpl,
    snapshots: () => Promise.resolve([]),
    players: () => Promise.resolve([]),
    listSessions: notImpl,
    createSession: notImpl,
    getSession: () => Promise.resolve({ meta: { id: 'sess', name: 'test', snapshot_id: 'demo-test', created_at: '', updated_at: '' }, state }),
    getState: () => Promise.resolve(state),
    deleteSession: notImpl,
    exportSession: notImpl,
    importSession: notImpl,
    appendEvent: notImpl,
    recommendFast: (_id, req) => Promise.resolve(makeRec(state, req.preview_player_id ? ['x', 'y'] : ['a', 'b', 'c'])),
    refine: () => Promise.reject(new ApiError(501, 'refine_unavailable', 'refinement layers are not available')),
    job: notImpl,
    compare: notImpl,
    profiles: notImpl,
    puntAdvisor: notImpl,
    template: () => Promise.reject(new Error('not implemented in fake')),
    importPreview: notImpl,
    importApply: notImpl,
    espnLinkPreview: notImpl,
    espnLinkApply: notImpl,
    espnSync: notImpl,
    seasonOverview: notImpl,
    seasonMatchup: notImpl,
    seasonFreeAgents: notImpl,
    seasonResults: notImpl,
    seasonPredictions: notImpl,
    seasonPerformers: notImpl,
    seasonMoves: async () => {
      throw new Error('not in test')
    },
    ...overrides,
  }
}

const fastDeps = { fastDelayMs: 0, refineDelayMs: 0, pollMs: 0, retryMs: 5 }

describe('store revision guard', () => {
  it('drops a fast recommendation whose ids no longer match the current state', async () => {
    const s0 = makeState()
    const slow = deferred<RecommendationResponse>()
    let calls = 0
    const api = fakeApi(s0, {
      recommendFast: () => {
        calls += 1
        return calls === 1 ? slow.promise : Promise.resolve(makeRec(s0, ['a', 'b']))
      },
    })
    const store = createDraftStore({ ...fastDeps, api, storage: memoryStorage() })
    await store.getState().loadSession('sess')
    await tick()
    expect(store.getState().recStatus).toBe('updating')
    // The draft moves on (revision 5) before the first recommendation returns.
    const s5 = { ...s0, draft_revision: 5, last_seq: 5 }
    store.setState({ state: s5 })
    slow.resolve(makeRec(s0, ['stale-player']))
    await tick()
    expect(store.getState().rec).toBeNull() // stale result dropped, never shown
    expect(selectRecCurrent(store.getState())).toBe(false)
  })

  it('shows a recommendation only when its ids match, and marks it stale after a strategy change', async () => {
    const s0 = makeState()
    const store = createDraftStore({ ...fastDeps, api: fakeApi(s0), storage: memoryStorage() })
    await store.getState().loadSession('sess')
    await tick(20)
    expect(store.getState().rec?.highlighted?.player_id).toBe('a')
    expect(selectRecCurrent(store.getState())).toBe(true)
    store.setState({ state: { ...s0, strategy_revision: 2 } })
    expect(selectRecCurrent(store.getState())).toBe(false)
    expect(store.getState().refineUnavailable).toBe(true) // 501 handled, not an error
  })

  it('ignores a slower, older fast request when a newer one already landed', async () => {
    const s0 = makeState()
    const first = deferred<RecommendationResponse>()
    let calls = 0
    const api = fakeApi(s0, {
      recommendFast: () => {
        calls += 1
        return calls === 1 ? first.promise : Promise.resolve(makeRec(s0, ['newer']))
      },
    })
    const store = createDraftStore({ ...fastDeps, api, storage: memoryStorage() })
    await store.getState().loadSession('sess')
    await tick()
    store.getState().requestRecommendation()
    await tick(20)
    expect(store.getState().rec?.highlighted?.player_id).toBe('newer')
    first.resolve(makeRec(s0, ['older']))
    await tick()
    expect(store.getState().rec?.highlighted?.player_id).toBe('newer')
  })
})

describe('optimistic commit, rollback and retry', () => {
  it('applies the pick immediately, then replaces state with the server response', async () => {
    const s0 = makeState()
    const serverAfter = applyLocalPick(s0, { player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    const pending = deferred<{ event: never; state: DraftStateView; deduplicated: boolean }>()
    const appendEvent = vi.fn(() => pending.promise)
    const storage = memoryStorage()
    let current = s0 // the fake server's current state: recommendations carry its revision ids
    const store = createDraftStore({
      ...fastDeps,
      api: fakeApi(s0, {
        appendEvent: appendEvent as unknown as ApiClient['appendEvent'],
        recommendFast: () => Promise.resolve(makeRec(current, ['a', 'b'])),
      }),
      storage,
    })
    await store.getState().loadSession('sess')
    await tick(20)
    const commit = store.getState().commitPick('demo:0001', 'm01')
    await tick()
    const mid = store.getState()
    expect(mid.state?.current_pick?.overall).toBe(2)
    expect(mid.state?.drafted_player_ids).toEqual(['demo:0001'])
    expect(mid.saveStatus).toBe('saving')
    expect(mid.pendingCommit?.expected_revision).toBe(s0.last_seq)
    expect(selectRecCurrent(mid)).toBe(false) // old recommendation no longer shown as current
    expect(storage.get(pendingKey('sess'))).not.toBeNull()
    const req = appendEvent.mock.calls[0] as unknown as [string, { payload: Record<string, unknown>; idempotency_key: string; expected_revision: number }]
    expect(req[1].payload).toEqual({ player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    expect(req[1].idempotency_key).toMatch(/\w+/)
    current = serverAfter
    pending.resolve({ event: undefined as never, state: serverAfter, deduplicated: false })
    await commit
    await tick(20)
    const done = store.getState()
    expect(done.saveStatus).toBe('saved')
    expect(done.pendingCommit).toBeNull()
    expect(done.state).toBe(serverAfter)
    expect(storage.get(pendingKey('sess'))).toBeNull()
    expect(done.rec?.ids.draft_revision).toBe(serverAfter.draft_revision)
  })

  it('rolls back to the previous state on a 422 and surfaces the server message', async () => {
    const s0 = makeState()
    const api = fakeApi(s0, { appendEvent: () => Promise.reject(new ApiError(422, 'duplicate_player', 'demo:0001 was already drafted')) })
    const store = createDraftStore({ ...fastDeps, api, storage: memoryStorage() })
    await store.getState().loadSession('sess')
    await tick(20)
    await store.getState().commitPick('demo:0001', 'm01')
    await tick(20)
    const s = store.getState()
    expect(s.state?.current_pick?.overall).toBe(1)
    expect(s.state?.drafted_player_ids).toEqual([])
    expect(s.pendingCommit).toBeNull()
    expect(s.saveStatus).toBe('saved')
    expect(s.notices.some((n) => n.kind === 'error' && n.text.includes('already drafted'))).toBe(true)
  })

  it('refetches state and warns on a 409 revision conflict', async () => {
    const s0 = makeState()
    const fresh = { ...s0, draft_revision: 3, last_seq: 3 }
    const api = fakeApi(s0, {
      appendEvent: () => Promise.reject(new ApiError(409, 'revision_conflict', 'revision conflict: expected 1, actual 3', { expected: 1, actual: 3 })),
      getState: () => Promise.resolve(fresh),
    })
    const store = createDraftStore({ ...fastDeps, api, storage: memoryStorage() })
    await store.getState().loadSession('sess')
    await tick(20)
    await store.getState().commitPick('demo:0001', 'm01')
    await tick(20)
    const s = store.getState()
    expect(s.state).toBe(fresh)
    expect(s.pendingCommit).toBeNull()
    expect(s.notices.some((n) => n.kind === 'warn' && /conflict/i.test(n.text))).toBe(true)
  })

  it('keeps the pick pending in storage on a network error and retries with the same idempotency key', async () => {
    const s0 = makeState()
    const serverAfter = applyLocalPick(s0, { player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    const keys: string[] = []
    let attempts = 0
    const api = fakeApi(s0, {
      appendEvent: (_id, req) => {
        attempts += 1
        keys.push(req.idempotency_key ?? '')
        if (attempts < 3) return Promise.reject(new ApiError(0, 'network', 'Failed to fetch'))
        return Promise.resolve({ event: undefined as never, state: serverAfter, deduplicated: attempts > 3 })
      },
    })
    const storage = memoryStorage()
    const store = createDraftStore({ ...fastDeps, api, storage })
    await store.getState().loadSession('sess')
    await tick(20)
    await store.getState().commitPick('demo:0001', 'm01')
    expect(store.getState().saveStatus).toBe('offline')
    expect(store.getState().state?.current_pick?.overall).toBe(2) // optimistic pick stays visible
    expect(JSON.parse(storage.get(pendingKey('sess')) ?? '{}').key).toBe(keys[0])
    await tick(40)
    expect(attempts).toBeGreaterThanOrEqual(3)
    expect(new Set(keys).size).toBe(1) // every retry reused the same key
    expect(store.getState().saveStatus).toBe('saved')
    expect(store.getState().pendingCommit).toBeNull()
    expect(storage.get(pendingKey('sess'))).toBeNull()
  })

  it('restores a persisted pending commit on reload and resends it', async () => {
    const s0 = makeState()
    const serverAfter = applyLocalPick(s0, { player_id: 'demo:0001', overall: 1, manager_id: 'm01' })
    const storage = memoryStorage()
    storage.set(pendingKey('sess'), JSON.stringify({ key: 'persisted-key', sessionId: 'sess', payload: { player_id: 'demo:0001', overall: 1, manager_id: 'm01' }, expected_revision: 1 }))
    const appendEvent = vi.fn(() => Promise.resolve({ event: undefined as never, state: serverAfter, deduplicated: true }))
    const store = createDraftStore({ ...fastDeps, api: fakeApi(s0, { appendEvent: appendEvent as unknown as ApiClient['appendEvent'] }), storage })
    await store.getState().loadSession('sess')
    await tick(20)
    expect(appendEvent).toHaveBeenCalledTimes(1)
    const req = appendEvent.mock.calls[0] as unknown as [string, { idempotency_key: string }]
    expect(req[1].idempotency_key).toBe('persisted-key')
    expect(store.getState().state).toBe(serverAfter)
    expect(store.getState().pendingCommit).toBeNull()
  })

  it('refuses a second commit while one is pending', async () => {
    const s0 = makeState()
    const never = deferred<never>()
    const store = createDraftStore({ ...fastDeps, api: fakeApi(s0, { appendEvent: () => never.promise }), storage: memoryStorage() })
    await store.getState().loadSession('sess')
    await tick(20)
    void store.getState().commitPick('demo:0001', 'm01')
    await tick()
    await store.getState().commitPick('demo:0002', 'm02')
    expect(store.getState().state?.current_pick?.overall).toBe(2)
    expect(store.getState().notices.some((n) => /still being saved/.test(n.text))).toBe(true)
  })
})
