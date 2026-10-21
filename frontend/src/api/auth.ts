import { API_BASE_URL } from '../utils/constants'

export interface AuthChallenge {
  challenge: string
  nonce: string
  expires_at: string
}

interface TokenResponse {
  access_token: string
  expires_in: number
}

let accessToken: string | null = null

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'same-origin',
    headers,
  })
  if (!response.ok) {
    throw new Error(`Authentication request failed with status ${response.status}`)
  }
  return (await response.json()) as T
}

export function getAccessToken(): string | null {
  return accessToken
}

export async function createChallenge(walletAddress: string): Promise<AuthChallenge> {
  return requestJson<AuthChallenge>('/auth/challenge', {
    method: 'POST',
    body: JSON.stringify({ wallet_address: walletAddress }),
  })
}

export async function verifyChallenge(
  walletAddress: string,
  signature: string,
  nonce: string,
): Promise<void> {
  const response = await requestJson<TokenResponse>('/auth/verify', {
    method: 'POST',
    body: JSON.stringify({ wallet_address: walletAddress, signature, nonce }),
  })
  accessToken = response.access_token
}

export async function refreshAccessToken(): Promise<void> {
  try {
    const response = await requestJson<TokenResponse>('/auth/refresh', { method: 'POST' })
    accessToken = response.access_token
  } catch (error) {
    accessToken = null
    throw error
  }
}

export async function logout(): Promise<void> {
  try {
    await requestJson<{ detail: string }>('/auth/logout', { method: 'POST' })
  } finally {
    accessToken = null
  }
}
