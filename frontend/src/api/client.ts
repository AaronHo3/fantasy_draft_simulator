// Thin typed fetch client. Every error becomes an ApiError with the server's code/message when present.
import type {
  CompareResponse,
  DraftStateView,
  EventRequest,
  EventResponse,
  FastRecommendRequest,
  HealthView,
  ImportApplyResponse,
  ImportKind,
  ImportPreviewView,
  JobAccepted,
  JobView,
  LeagueProfilesResponse,
  PuntAdvisorResponse,
  PlayerView,
  RecommendationResponse,
  RefineRequest,
  SessionCreate,
  SessionDetail,
  SessionSummary,
  SnapshotMeta,
  LinkRequest,
  LinkPreview,
  LinkApplyRequest,
  SyncResult,
  SeasonOverview,
  MatchupResponse,
  FreeAgentsResponse,
  WeekResultsResponse,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: Record<string, unknown>

  constructor(status: number, code: string, message: string, detail: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }

  get isNetwork(): boolean {
    return this.status === 0
  }
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

interface ValidationItem {
  loc?: (string | number)[]
  msg?: string
}

function describeValidation(items: ValidationItem[]): string {
  return items
    .map((it) => `${(it.loc ?? []).filter((x) => x !== 'body').join('.')}: ${it.msg ?? 'invalid'}`)
    .join('; ')
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    return new ApiError(res.status, `http_${res.status}`, res.statusText || `HTTP ${res.status}`)
  }
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>
    if (typeof b.code === 'string') {
      return new ApiError(res.status, b.code, String(b.message ?? b.code), (b.detail as Record<string, unknown>) ?? {})
    }
    const detail = b.detail
    if (Array.isArray(detail)) {
      return new ApiError(res.status, 'validation_error', describeValidation(detail as ValidationItem[]))
    }
    if (detail && typeof detail === 'object') {
      const d = detail as Record<string, unknown>
      return new ApiError(res.status, String(d.code ?? `http_${res.status}`), String(d.message ?? res.statusText))
    }
    if (typeof detail === 'string') return new ApiError(res.status, `http_${res.status}`, detail)
  }
  return new ApiError(res.status, `http_${res.status}`, res.statusText || `HTTP ${res.status}`)
}

export interface ApiClient {
  health(): Promise<HealthView>
  snapshots(): Promise<SnapshotMeta[]>
  players(snapshotId: string, opts?: { q?: string; limit?: number; sessionId?: string | null }): Promise<PlayerView[]>
  listSessions(): Promise<SessionSummary[]>
  createSession(body: SessionCreate): Promise<SessionSummary>
  getSession(id: string): Promise<SessionDetail>
  getState(id: string): Promise<DraftStateView>
  deleteSession(id: string): Promise<void>
  exportSession(id: string): Promise<Record<string, unknown>>
  importSession(body: Record<string, unknown>): Promise<SessionSummary>
  appendEvent(id: string, req: EventRequest): Promise<EventResponse>
  recommendFast(id: string, req: FastRecommendRequest): Promise<RecommendationResponse>
  refine(id: string, req: RefineRequest): Promise<JobAccepted>
  job(jobId: string, sessionId: string): Promise<JobView>
  compare(id: string, playerIds: string[]): Promise<CompareResponse>
  profiles(id: string): Promise<LeagueProfilesResponse>
  puntAdvisor(id: string, budgetMs: number): Promise<PuntAdvisorResponse>
  template(kind: ImportKind): Promise<string>
  importPreview(id: string, kind: ImportKind, text: string): Promise<ImportPreviewView>
  importApply(id: string, kind: ImportKind, text: string, skipErrorRows: boolean, expectedRevision?: number | null): Promise<ImportApplyResponse>
  espnLinkPreview(id: string, body: LinkRequest): Promise<LinkPreview>
  espnLinkApply(id: string, body: LinkApplyRequest): Promise<SessionDetail>
  espnSync(id: string, expectedRevision?: number | null): Promise<SyncResult>
  seasonOverview(id: string, opts?: { seed?: number; period?: number | null }): Promise<SeasonOverview>
  seasonMatchup(id: string, period: number, teamA: string, teamB: string): Promise<MatchupResponse>
  seasonFreeAgents(id: string, opts?: { limit?: number; position?: string | null; q?: string | null }): Promise<FreeAgentsResponse>
  seasonResults(id: string, period: number): Promise<WeekResultsResponse>
}

export function createApiClient(fetchImpl: FetchLike = (i, o) => fetch(i, o), base = '/api'): ApiClient {
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    let res: Response
    try {
      res = await fetchImpl(base + path, {
        method,
        headers: body === undefined ? undefined : { 'content-type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch (e) {
      throw new ApiError(0, 'network', e instanceof Error ? e.message : 'network error')
    }
    if (!res.ok) throw await toApiError(res)
    if (res.status === 204) return undefined as T
    return (await res.json()) as T
  }

  const qs = (params: Record<string, string | number | null | undefined>) => {
    const u = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') u.set(k, String(v))
    const s = u.toString()
    return s ? `?${s}` : ''
  }

  return {
    health: () => request('GET', '/health'),
    snapshots: () => request('GET', '/snapshots'),
    players: (snapshotId, opts = {}) =>
      request('GET', `/snapshots/${encodeURIComponent(snapshotId)}/players${qs({ q: opts.q, limit: opts.limit, session_id: opts.sessionId })}`),
    listSessions: () => request('GET', '/sessions'),
    createSession: (body) => request('POST', '/sessions', body),
    getSession: (id) => request('GET', `/sessions/${encodeURIComponent(id)}`),
    getState: (id) => request('GET', `/sessions/${encodeURIComponent(id)}/state`),
    deleteSession: (id) => request('DELETE', `/sessions/${encodeURIComponent(id)}`),
    exportSession: (id) => request('GET', `/sessions/${encodeURIComponent(id)}/export`),
    importSession: (body) => request('POST', '/sessions/import', body),
    appendEvent: (id, req) => request('POST', `/sessions/${encodeURIComponent(id)}/events`, req),
    recommendFast: (id, req) => request('POST', `/sessions/${encodeURIComponent(id)}/recommend/fast`, req),
    refine: (id, req) => request('POST', `/sessions/${encodeURIComponent(id)}/recommend/refine`, req),
    job: (jobId, sessionId) => request('GET', `/jobs/${encodeURIComponent(jobId)}${qs({ session_id: sessionId })}`),
    compare: (id, playerIds) => request('POST', `/sessions/${encodeURIComponent(id)}/compare`, { player_ids: playerIds }),
    profiles: (id) => request('GET', `/sessions/${encodeURIComponent(id)}/profiles`),
    puntAdvisor: (id, budgetMs) => request('POST', `/sessions/${encodeURIComponent(id)}/punt-advisor`, { budget_ms: budgetMs }),
    template: async (kind) => {
      let res: Response
      try {
        res = await fetchImpl(`${base}/templates/${kind}`)
      } catch (e) {
        throw new ApiError(0, 'network', e instanceof Error ? e.message : 'network error')
      }
      if (!res.ok) throw await toApiError(res)
      return res.text()
    },
    importPreview: (id, kind, text) => request('POST', `/sessions/${encodeURIComponent(id)}/import/preview`, { kind, text }),
    importApply: (id, kind, text, skipErrorRows, expectedRevision = null) =>
      request('POST', `/sessions/${encodeURIComponent(id)}/import/apply`, { kind, text, skip_error_rows: skipErrorRows, expected_revision: expectedRevision }),
    espnLinkPreview: (id, body) => request('POST', `/sessions/${encodeURIComponent(id)}/espn/link`, body),
    espnLinkApply: (id, body) => request('POST', `/sessions/${encodeURIComponent(id)}/espn/link/apply`, body),
    espnSync: (id, expectedRevision = null) =>
      request('POST', `/sessions/${encodeURIComponent(id)}/espn/sync`, { expected_revision: expectedRevision }),
    seasonOverview: (id, opts = {}) =>
      request('GET', `/sessions/${encodeURIComponent(id)}/season/overview${qs({ seed: opts.seed, period: opts.period })}`),
    seasonMatchup: (id, period, teamA, teamB) =>
      request('GET', `/sessions/${encodeURIComponent(id)}/season/matchup${qs({ period, team_a: teamA, team_b: teamB })}`),
    seasonFreeAgents: (id, opts = {}) =>
      request('GET', `/sessions/${encodeURIComponent(id)}/season/free-agents${qs({ limit: opts.limit, position: opts.position, q: opts.q })}`),
    seasonResults: (id, period) => request('GET', `/sessions/${encodeURIComponent(id)}/season/results${qs({ period })}`),
  }
}

export const api: ApiClient = createApiClient()
