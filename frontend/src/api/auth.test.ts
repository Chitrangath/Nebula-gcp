import { afterEach, describe, expect, it, vi } from 'vitest'

const tokenResponse = (accessToken: string): Response =>
  new Response(JSON.stringify({ access_token: accessToken, expires_in: 86400 }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

async function freshAuthModule() {
  vi.resetModules()
  return import('./auth')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('browser authentication token ownership', () => {
  it('keeps the verified access token only in module memory', async () => {
    const fetchMock = vi.fn().mockResolvedValue(tokenResponse('verified-token'))
    vi.stubGlobal('fetch', fetchMock)
    const auth = await freshAuthModule()

    await auth.verifyChallenge('0x' + '11'.repeat(20), '0xsigned', 'nonce')

    expect(auth.getAccessToken()).toBe('verified-token')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/auth/verify',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    )
  })

  it('replaces the access token after refresh', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(tokenResponse('first-token'))
      .mockResolvedValueOnce(tokenResponse('rotated-token'))
    vi.stubGlobal('fetch', fetchMock)
    const auth = await freshAuthModule()

    await auth.verifyChallenge('0x' + '11'.repeat(20), '0xsigned', 'nonce')
    await auth.refreshAccessToken()

    expect(auth.getAccessToken()).toBe('rotated-token')
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/v1/auth/refresh',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
    )
  })

  it('clears memory after failed refresh and logout', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(tokenResponse('first-token'))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Logged out' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const auth = await freshAuthModule()

    await auth.verifyChallenge('0x' + '11'.repeat(20), '0xsigned', 'nonce')
    await expect(auth.refreshAccessToken()).rejects.toThrow('status 401')
    expect(auth.getAccessToken()).toBeNull()
    await auth.logout()
    expect(auth.getAccessToken()).toBeNull()
  })
})
