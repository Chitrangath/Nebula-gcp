import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiProblemError, ApiUnavailableError, requestApi } from './client'
import { clearAccessToken, enableSessionRefresh, getAccessToken, invalidateSession, setAccessToken } from './session'

describe('typed API client', () => {
  beforeEach(() => {
    clearAccessToken()
    enableSessionRefresh()
    vi.restoreAllMocks()
  })

  it('refreshes once after an expired access token and retries the request', async () => {
    setAccessToken('expired')
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'fresh', expires_in: 60 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    await expect(requestApi<{ ok: boolean }>('/jobs', { method: 'GET' })).resolves.toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(getAccessToken()).toBe('fresh')
    expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get('Authorization')).toBe('Bearer fresh')
  })

  it('clears the session when refresh fails without retrying again', async () => {
    setAccessToken('expired')
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ title: 'Unauthorized', status: 401, detail: 'expired', type: 'about:blank', instance: '/auth/refresh' }), { status: 401, headers: { 'Content-Type': 'application/problem+json' } }))

    await expect(requestApi('/jobs', { method: 'GET' })).rejects.toBeInstanceOf(ApiProblemError)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(getAccessToken()).toBeNull()

    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 401 }))
    await expect(requestApi('/jobs', { method: 'GET' })).rejects.toBeInstanceOf(ApiProblemError)
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('propagates cancellation to fetch', async () => {
    const controller = new AbortController()
    controller.abort()
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new DOMException('Aborted', 'AbortError'))

    await expect(requestApi('/jobs', { method: 'GET', signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    expect(fetch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ signal: controller.signal }))
  })

  it('turns network details into a safe availability error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('getaddrinfo ENOTFOUND internal-host'))

    await expect(requestApi('/jobs', { method: 'GET' })).rejects.toEqual(new ApiUnavailableError())
  })

  it('preserves server validation detail for user-facing correction guidance', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      title: 'Request failed', status: 422, detail: 'input MIME type does not match its extension', type: 'about:blank', instance: '/jobs',
    }), { status: 422, headers: { 'Content-Type': 'application/problem+json' } }))

    await expect(requestApi('/jobs', { method: 'GET' })).rejects.toMatchObject({
      name: 'ApiProblemError', status: 422, detail: 'input MIME type does not match its extension',
    })
  })

  it('shares one refresh across concurrent expired requests', async () => {
    setAccessToken('expired')
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    fetchMock.mockImplementation(async (url) => {
      if (String(url).endsWith('/auth/refresh')) {
        await Promise.resolve()
        return new Response(JSON.stringify({ access_token: 'fresh', expires_in: 60 }), { status: 200 })
      }
      const currentCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]
      const authorization = new Headers(currentCall?.[1]?.headers).get('Authorization')
      return authorization === 'Bearer fresh'
        ? new Response(JSON.stringify({ ok: true }), { status: 200 })
        : new Response(null, { status: 401 })
    })

    await expect(Promise.all([
      requestApi<{ ok: boolean }>('/jobs/one', { method: 'GET' }),
      requestApi<{ ok: boolean }>('/jobs/two', { method: 'GET' }),
    ])).resolves.toEqual([{ ok: true }, { ok: true }])
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/auth/refresh'))).toHaveLength(1)
  })

  it('does not restore the previous wallet through refresh after invalidation', async () => {
    invalidateSession()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 401 }))

    await expect(requestApi('/jobs', { method: 'GET' })).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('discards a stale refresh response when the wallet changes in flight', async () => {
    setAccessToken('expired')
    let finishRefresh: ((response: Response) => void) | undefined
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockImplementationOnce(() => new Promise((resolve) => { finishRefresh = resolve }))

    const request = requestApi('/jobs', { method: 'GET' })
    await vi.waitFor(() => expect(finishRefresh).toBeDefined())
    invalidateSession()
    const resolveRefresh = finishRefresh as ((response: Response) => void) | undefined
    resolveRefresh?.(new Response(JSON.stringify({ access_token: 'stale', expires_in: 60 }), { status: 200 }))

    await expect(request).rejects.toMatchObject({ status: 401 })
    expect(getAccessToken()).toBeNull()
  })
})
