import { beforeEach, describe, expect, it } from 'vitest'

import { canRefreshSession, clearAccessToken, enableSessionRefresh, getAccessToken, invalidateSession, setAccessToken } from './session'

describe('in-memory access token session', () => {
  beforeEach(() => {
    clearAccessToken()
    enableSessionRefresh()
  })

  it('keeps and clears the token without browser persistence', () => {
    setAccessToken('secret-token')
    expect(getAccessToken()).toBe('secret-token')
    expect(localStorage).toHaveLength(0)
    expect(sessionStorage).toHaveLength(0)

    clearAccessToken()
    expect(getAccessToken()).toBeNull()
  })

  it('blocks cookie refresh after wallet identity invalidation until authentication succeeds', () => {
    invalidateSession()
    expect(canRefreshSession()).toBe(false)
    enableSessionRefresh()
    expect(canRefreshSession()).toBe(true)
  })
})
