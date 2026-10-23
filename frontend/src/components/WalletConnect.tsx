import { useEffect, useRef, useState } from 'react'

import { ApiUnavailableError } from '../api/client'
import { authenticateWallet } from '../api/auth'
import { invalidateSession } from '../api/session'
import {
  subscribeToWalletInvalidation,
  type ConnectedWallet,
  type Eip1193Provider,
  WalletRejectedError,
  WrongChainError,
} from '../wallet/wallet'

interface WalletConnectProps {
  provider?: Eip1193Provider
}

function displayError(error: unknown): string {
  if (error instanceof WrongChainError) return error.message
  if (error instanceof WalletRejectedError) return 'Wallet connection was cancelled'
  if (error instanceof ApiUnavailableError) return error.message
  return 'Wallet authentication failed. Please try again.'
}

function shortAddress(address: string): string {
  return `${address.slice(0, 6)}…${address.slice(-4)}`
}

export default function WalletConnect({ provider = window.ethereum }: WalletConnectProps) {
  const [wallet, setWallet] = useState<ConnectedWallet | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestController = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!provider) return
    return subscribeToWalletInvalidation(provider, () => {
      requestController.current?.abort()
      invalidateSession()
      setWallet(null)
      setConnecting(false)
      setError(null)
    })
  }, [provider])

  useEffect(() => () => requestController.current?.abort(), [])

  async function connect(): Promise<void> {
    if (!provider) {
      setError('Install an EIP-1193 wallet such as MetaMask to continue')
      return
    }
    requestController.current?.abort()
    const controller = new AbortController()
    requestController.current = controller
    setConnecting(true)
    setError(null)
    try {
      setWallet(await authenticateWallet(provider, controller.signal))
    } catch (caught) {
      if (!controller.signal.aborted) setError(displayError(caught))
    } finally {
      if (!controller.signal.aborted) setConnecting(false)
    }
  }

  return (
    <div className="flex flex-col items-end">
      <button
        type="button"
        onClick={() => void connect()}
        disabled={connecting || wallet !== null}
        aria-label={wallet ? `Connected wallet ${shortAddress(wallet.address)}` : undefined}
        className="bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 disabled:opacity-60"
      >
        {connecting ? 'Connecting…' : wallet ? shortAddress(wallet.address) : 'Connect Wallet'}
      </button>
      {error ? <p role="alert" className="absolute mt-11 max-w-xs text-sm text-red-700">{error}</p> : null}
    </div>
  )
}
