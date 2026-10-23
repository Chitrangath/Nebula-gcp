import { ARBITRUM_SEPOLIA_CHAIN_ID } from '../utils/constants'

export interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>
  on?(event: 'accountsChanged' | 'chainChanged', listener: (...args: unknown[]) => void): void
  removeListener?(event: 'accountsChanged' | 'chainChanged', listener: (...args: unknown[]) => void): void
}

export interface ConnectedWallet {
  address: `0x${string}`
  chainId: number
}

export class WalletRejectedError extends Error {
  constructor() {
    super('Wallet request was rejected')
    this.name = 'WalletRejectedError'
  }
}

export class WrongChainError extends Error {
  readonly chainId: number

  constructor(chainId: number) {
    super(`Switch wallet to Arbitrum Sepolia (${ARBITRUM_SEPOLIA_CHAIN_ID})`)
    this.name = 'WrongChainError'
    this.chainId = chainId
  }
}

export async function connectInjectedWallet(provider: Eip1193Provider): Promise<ConnectedWallet> {
  try {
    const accounts = (await provider.request({ method: 'eth_requestAccounts' })) as unknown[]
    const chainValue = await provider.request({ method: 'eth_chainId' })
    const address = accounts[0]
    if (typeof address !== 'string' || !/^0x[0-9a-fA-F]{40}$/.test(address)) {
      throw new WalletRejectedError()
    }
    const chainId = Number.parseInt(String(chainValue), 16)
    if (chainId !== ARBITRUM_SEPOLIA_CHAIN_ID) {
      throw new WrongChainError(chainId)
    }
    return { address: address.toLowerCase() as `0x${string}`, chainId }
  } catch (error) {
    if (error instanceof WrongChainError || error instanceof WalletRejectedError) {
      throw error
    }
    throw new WalletRejectedError()
  }
}

export function subscribeToWalletInvalidation(provider: Eip1193Provider, invalidate: () => void): () => void {
  const onAccountsChanged = () => invalidate()
  const onChainChanged = () => invalidate()
  provider.on?.('accountsChanged', onAccountsChanged)
  provider.on?.('chainChanged', onChainChanged)
  return () => {
    provider.removeListener?.('accountsChanged', onAccountsChanged)
    provider.removeListener?.('chainChanged', onChainChanged)
  }
}
