import { expect, test } from '@playwright/test'
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts'

test('deployed same-origin authentication rotates and clears its secure cookie', async ({ browser, baseURL }) => {
  expect(baseURL).toBeTruthy()
  const origin = new URL(baseURL!).origin
  expect(baseURL).toBe(origin)

  const context = await browser.newContext({
    baseURL: origin,
  })
  const account = privateKeyToAccount(generatePrivateKey())
  const page = await context.newPage()
  await page.goto(origin)
  expect(await page.evaluate(() => localStorage.length)).toBe(0)
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0)

  const challengeResponse = await page.evaluate(async (walletAddress) => {
    const response = await fetch('/api/v1/auth/challenge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet_address: walletAddress }),
    })
    return {
      ok: response.ok,
      url: response.url,
      cacheControl: response.headers.get('cache-control'),
      body: (await response.json()) as { challenge: string; nonce: string },
    }
  }, account.address.toLowerCase())
  expect(challengeResponse.ok).toBe(true)
  expect(challengeResponse.cacheControl).toContain('no-store')
  expect(challengeResponse.url).toMatch(
    new RegExp(`^${origin.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/api/v1/`),
  )
  const challenge = challengeResponse.body
  const signature = await account.signMessage({ message: challenge.challenge })

  const verifyResponse = await page.evaluate(async (payload) => {
    const response = await fetch('/api/v1/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return {
      ok: response.ok,
      cacheControl: response.headers.get('cache-control'),
      allowedOrigin: response.headers.get('access-control-allow-origin'),
    }
  }, {
      wallet_address: account.address.toLowerCase(),
      signature,
      nonce: challenge.nonce,
  })
  expect(verifyResponse.ok).toBe(true)
  expect(verifyResponse.cacheControl).toContain('no-store')
  expect(verifyResponse.allowedOrigin).toBe(origin)
  expect(await page.evaluate(() => localStorage.length)).toBe(0)
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0)

  const verifiedCookies = await context.cookies(origin)
  const originalRefresh = verifiedCookies.find((cookie) => cookie.name === 'refresh_token')
  expect(originalRefresh).toMatchObject({
    domain: new URL(origin).hostname,
    httpOnly: true,
    secure: true,
    sameSite: 'Strict',
    path: '/api/v1/auth',
  })

  const refreshStatus = await page.evaluate(async () => {
    const response = await fetch('/api/v1/auth/refresh', { method: 'POST' })
    return response.status
  })
  expect(refreshStatus).toBe(200)
  expect(await page.evaluate(() => localStorage.length)).toBe(0)
  expect(await page.evaluate(() => sessionStorage.length)).toBe(0)
  const rotatedRefresh = (await context.cookies(origin)).find((cookie) => cookie.name === 'refresh_token')
  expect(rotatedRefresh?.value).toBeTruthy()
  expect(rotatedRefresh?.value).not.toBe(originalRefresh?.value)

  const logoutStatus = await page.evaluate(async () => {
    const response = await fetch('/api/v1/auth/logout', { method: 'POST' })
    return response.status
  })
  expect(logoutStatus).toBe(200)
  expect((await context.cookies(origin)).find((cookie) => cookie.name === 'refresh_token')).toBeUndefined()

  const rejectedRefreshStatus = await page.evaluate(async () => {
    const response = await fetch('/api/v1/auth/refresh', { method: 'POST' })
    return response.status
  })
  expect(rejectedRefreshStatus).toBe(401)
  await context.close()
})
