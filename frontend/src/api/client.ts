import type { components } from './schema'
import { API_BASE_URL } from '../utils/constants'
import { canRefreshSession, getAccessToken, getSessionGeneration, invalidateSession, setAccessToken } from './session'

type Problem = components['schemas']['ProblemResponse']
type RefreshResponse = components['schemas']['RefreshResponse']

export class ApiProblemError extends Error {
  readonly status: number
  readonly type: string

  constructor(problem: Pick<Problem, 'title' | 'status' | 'type'>) {
    super(problem.title || 'Request failed')
    this.name = 'ApiProblemError'
    this.status = problem.status
    this.type = problem.type
  }
}

export class ApiUnavailableError extends Error {
  constructor() {
    super('The Nebula service is temporarily unavailable')
    this.name = 'ApiUnavailableError'
  }
}

async function fetchApi(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined) headers.set('Content-Type', 'application/json')
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  try {
    return await fetch(`${API_BASE_URL}${path}`, { ...init, credentials: 'same-origin', headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiUnavailableError()
  }
}

async function problemFrom(response: Response): Promise<ApiProblemError> {
  try {
    const problem = (await response.json()) as Partial<Problem>
    return new ApiProblemError({
      title: typeof problem.title === 'string' ? problem.title : 'Request failed',
      status: response.status,
      type: typeof problem.type === 'string' ? problem.type : 'about:blank',
    })
  } catch {
    return new ApiProblemError({ title: 'Request failed', status: response.status, type: 'about:blank' })
  }
}

let refreshInFlight: Promise<void> | null = null

async function refresh(): Promise<void> {
  const generation = getSessionGeneration()
  const response = await fetchApi('/auth/refresh', { method: 'POST' })
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) invalidateSession()
    throw await problemFrom(response)
  }
  const body = (await response.json()) as RefreshResponse
  if (generation !== getSessionGeneration() || !canRefreshSession()) {
    throw new ApiProblemError({ title: 'Wallet session changed', status: 401, type: 'about:blank' })
  }
  setAccessToken(body.access_token)
}

function sharedRefresh(): Promise<void> {
  if (!refreshInFlight) {
    refreshInFlight = refresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

export async function requestApi<T>(path: string, init: RequestInit, allowRefresh = true): Promise<T> {
  let response = await fetchApi(path, init)
  if (response.status === 401 && allowRefresh && canRefreshSession() && !path.startsWith('/auth/')) {
    await sharedRefresh()
    init.signal?.throwIfAborted()
    response = await fetchApi(path, init)
  }
  if (!response.ok) throw await problemFrom(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
