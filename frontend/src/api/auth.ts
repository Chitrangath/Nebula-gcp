import type { components } from './schema'
import { requestApi } from './client'
import { enableSessionRefresh, getAccessToken, invalidateSession, setAccessToken, setAuthenticatedWallet } from './session'
import { connectInjectedWallet, restoreInjectedWallet, type ConnectedWallet, type Eip1193Provider } from '../wallet/wallet'

export type AuthChallenge = components['schemas']['ChallengeResponse']
type ChallengeRequest = components['schemas']['ChallengeRequest']
type VerifyRequest = components['schemas']['VerifyRequest']
type VerifyResponse = components['schemas']['VerifyResponse']

export { getAccessToken }

export async function createChallenge(walletAddress: string, signal?: AbortSignal): Promise<AuthChallenge> {
  const body: ChallengeRequest = { wallet_address: walletAddress }
  return requestApi<AuthChallenge>('/auth/challenge', { method: 'POST', body: JSON.stringify(body), signal }, false)
}

export async function verifyChallenge(
  walletAddress: string,
  signature: string,
  nonce: string,
  signal?: AbortSignal,
): Promise<void> {
  const body: VerifyRequest = { wallet_address: walletAddress, signature, nonce }
  const response = await requestApi<VerifyResponse>('/auth/verify', { method: 'POST', body: JSON.stringify(body), signal }, false)
  setAccessToken(response.access_token)
}

export async function authenticateWallet(provider: Eip1193Provider, signal?: AbortSignal): Promise<ConnectedWallet> {
  const wallet = await connectInjectedWallet(provider)
  signal?.throwIfAborted()
  const challenge = await createChallenge(wallet.address, signal)
  signal?.throwIfAborted()
  const signature = await provider.request({ method: 'personal_sign', params: [challenge.challenge, wallet.address] })
  signal?.throwIfAborted()
  if (typeof signature !== 'string') throw new Error('Wallet returned an invalid signature')
  await verifyChallenge(wallet.address, signature, challenge.nonce, signal)
  setAuthenticatedWallet(wallet.address)
  enableSessionRefresh()
  return wallet
}

export async function restoreWalletSession(provider: Eip1193Provider, signal?: AbortSignal): Promise<ConnectedWallet | null> {
  const wallet = await restoreInjectedWallet(provider)
  if (!wallet) return null
  try {
    const response = await requestApi<VerifyResponse>('/auth/refresh', { method: 'POST', signal }, false)
    setAccessToken(response.access_token)
    setAuthenticatedWallet(wallet.address)
    enableSessionRefresh()
    return wallet
  } catch {
    return null
  }
}

export async function logout(signal?: AbortSignal): Promise<void> {
  try {
    await requestApi<Record<string, string>>('/auth/logout', { method: 'POST', signal }, false)
  } finally {
    invalidateSession()
  }
}
