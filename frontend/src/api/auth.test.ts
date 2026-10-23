import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authenticateWallet, logout } from './auth'
import { clearAccessToken, enableSessionRefresh, getAccessToken, getAuthenticatedWallet, setAccessToken } from './session'

const address = `0x${'12'.repeat(20)}`
const chainId = '0x66eee'

describe('wallet authentication', () => {
  beforeEach(() => {
    clearAccessToken()
    enableSessionRefresh()
    vi.restoreAllMocks()
  })

  it('signs the exact expiring challenge and keeps the returned token in memory', async () => {
    const request = vi.fn(async ({ method, params }: { method: string; params?: unknown[] }) => {
      if (method === 'eth_requestAccounts') return [address]
      if (method === 'eth_chainId') return chainId
      if (method === 'personal_sign') {
        expect(params).toEqual(['Sign this exact challenge', address])
        return `0x${'ab'.repeat(65)}`
      }
      throw new Error('unexpected method')
    })
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ challenge: 'Sign this exact challenge', nonce: 'nonce-1', expires_at: '2099-01-01T00:00:00Z' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'access', expires_in: 60 }), { status: 200 }))

    await expect(authenticateWallet({ request })).resolves.toMatchObject({ address: address.toLowerCase() })
    expect(getAccessToken()).toBe('access')
    expect(getAuthenticatedWallet()).toBe(address)
  })

  it('aborts challenge fetch when its caller cancels', async () => {
    const controller = new AbortController()
    const request = vi.fn().mockResolvedValueOnce([address]).mockResolvedValueOnce(chainId)
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
      expect(init?.signal).toBe(controller.signal)
      throw new DOMException('Aborted', 'AbortError')
    })
    controller.abort()

    await expect(authenticateWallet({ request }, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('clears the token even when remote logout is unavailable', async () => {
    setAccessToken('access')
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network detail'))

    await expect(logout()).rejects.toThrow('temporarily unavailable')
    expect(getAccessToken()).toBeNull()
  })
})
