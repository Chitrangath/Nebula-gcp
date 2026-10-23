import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearAccessToken, getAccessToken } from '../api/session'
import type { Eip1193Provider } from '../wallet/wallet'
import WalletConnect from './WalletConnect'

const address = `0x${'34'.repeat(20)}`

function providerFor(chainId = '0x66eee'): Eip1193Provider {
  return {
    request: vi.fn(async ({ method }) => {
      if (method === 'eth_requestAccounts') return [address]
      if (method === 'eth_chainId') return chainId
      if (method === 'personal_sign') return `0x${'cd'.repeat(65)}`
      throw new Error('unexpected wallet method')
    }),
    on: vi.fn(),
    removeListener: vi.fn(),
  }
}

describe('WalletConnect', () => {
  beforeEach(clearAccessToken)
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('connects, signs, and shows the shortened wallet address', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ challenge: 'challenge', nonce: 'nonce', expires_at: '2099-01-01T00:00:00Z' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'access', expires_in: 60 }), { status: 200 }))
    render(<WalletConnect provider={providerFor()} />)

    await userEvent.click(screen.getByRole('button', { name: 'Connect Wallet' }))

    expect(await screen.findByRole('button', { name: 'Connected wallet 0x3434…3434' })).toBeInTheDocument()
    expect(getAccessToken()).toBe('access')
  })

  it('shows an actionable wrong-network message without provider details', async () => {
    render(<WalletConnect provider={providerFor('0x1')} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Wallet' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Switch wallet to Arbitrum Sepolia')
  })

  it('clears authentication when the account changes', async () => {
    const listeners = new Map<string, (...args: unknown[]) => void>()
    const provider = providerFor()
    provider.on = vi.fn((event, listener) => listeners.set(event, listener))
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ challenge: 'challenge', nonce: 'nonce', expires_at: '2099-01-01T00:00:00Z' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'access', expires_in: 60 }), { status: 200 }))
    render(<WalletConnect provider={provider} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Wallet' }))
    await screen.findByText('0x3434…3434')

    act(() => listeners.get('accountsChanged')?.([]))

    await waitFor(() => expect(screen.getByText('Connect Wallet')).toBeInTheDocument())
    expect(getAccessToken()).toBeNull()
  })

  it('aborts an in-flight backend request when unmounted', async () => {
    let observedSignal: AbortSignal | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((_url, init) => {
      observedSignal = init?.signal as AbortSignal
      return new Promise(() => undefined)
    })
    const { unmount } = render(<WalletConnect provider={providerFor()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Wallet' }))
    await waitFor(() => expect(observedSignal).not.toBeNull())

    unmount()
    expect((observedSignal as AbortSignal | null)?.aborted).toBe(true)
  })

  it('ignores a late provider failure after wallet invalidation', async () => {
    const listeners = new Map<string, (...args: unknown[]) => void>()
    let rejectRequest: ((reason: Error) => void) | undefined
    const provider: Eip1193Provider = {
      request: vi.fn(() => new Promise((_resolve, reject) => { rejectRequest = reject })),
      on: vi.fn((event, listener) => listeners.set(event, listener)),
      removeListener: vi.fn(),
    }
    render(<WalletConnect provider={provider} />)
    await userEvent.click(screen.getByRole('button', { name: 'Connect Wallet' }))

    act(() => listeners.get('chainChanged')?.('0x1'))
    await act(async () => rejectRequest?.(new Error('late provider detail')))

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect Wallet' })).toBeEnabled()
  })
})
