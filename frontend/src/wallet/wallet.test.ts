import { describe, expect, it, vi } from 'vitest'

import { ARBITRUM_SEPOLIA_CHAIN_ID } from '../utils/constants'
import { connectInjectedWallet, subscribeToWalletInvalidation, WalletRejectedError, WrongChainError } from './wallet'

const chainHex = `0x${ARBITRUM_SEPOLIA_CHAIN_ID.toString(16)}`

describe('injected wallet adapter', () => {
  it('connects only an Arbitrum Sepolia account', async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce(['0x' + '11'.repeat(20)])
      .mockResolvedValueOnce(chainHex)

    const wallet = await connectInjectedWallet({ request })

    expect(wallet).toEqual({ address: '0x' + '11'.repeat(20), chainId: ARBITRUM_SEPOLIA_CHAIN_ID })
  })

  it('reports user rejection without leaking provider errors', async () => {
    const request = vi.fn().mockRejectedValue(new Error('provider internals'))

    await expect(connectInjectedWallet({ request })).rejects.toBeInstanceOf(WalletRejectedError)
  })

  it('rejects the wrong chain deterministically', async () => {
    const request = vi.fn().mockResolvedValueOnce(['0x' + '22'.repeat(20)]).mockResolvedValueOnce('0x1')

    await expect(connectInjectedWallet({ request })).rejects.toEqual(new WrongChainError(1))
  })

  it.each(['accountsChanged', 'chainChanged'] as const)('invalidates and unsubscribes on %s', (event) => {
    const listeners = new Map<string, (...args: unknown[]) => void>()
    const provider = {
      request: vi.fn(),
      on: vi.fn((name: string, listener: (...args: unknown[]) => void) => listeners.set(name, listener)),
      removeListener: vi.fn(),
    }
    const invalidate = vi.fn()
    const unsubscribe = subscribeToWalletInvalidation(provider, invalidate)

    listeners.get(event)?.('changed')
    expect(invalidate).toHaveBeenCalledOnce()
    unsubscribe()
    expect(provider.removeListener).toHaveBeenCalledTimes(2)
  })
})
