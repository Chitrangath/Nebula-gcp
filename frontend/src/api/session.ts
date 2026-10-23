let accessToken: string | null = null
let refreshAllowed = true
let sessionGeneration = 0
let authenticatedWallet: `0x${string}` | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string): void {
  accessToken = token
}

export function clearAccessToken(): void {
  accessToken = null
}

export function invalidateSession(): void {
  accessToken = null
  authenticatedWallet = null
  refreshAllowed = false
  sessionGeneration += 1
}

export function enableSessionRefresh(): void {
  refreshAllowed = true
}

export function canRefreshSession(): boolean {
  return refreshAllowed
}

export function getSessionGeneration(): number {
  return sessionGeneration
}

export function setAuthenticatedWallet(address: `0x${string}`): void {
  authenticatedWallet = address.toLowerCase() as `0x${string}`
}

export function getAuthenticatedWallet(): `0x${string}` | null {
  return authenticatedWallet
}
