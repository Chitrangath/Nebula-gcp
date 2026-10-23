let accessToken: string | null = null
let refreshAllowed = true
let sessionGeneration = 0

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
