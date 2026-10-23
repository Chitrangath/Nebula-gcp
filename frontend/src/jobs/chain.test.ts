import { describe, expect, it } from 'vitest'

import { isDefinitivelyDropped } from './chain'

describe('chain transaction reconciliation', () => {
  it('classifies an absent transaction as dropped only while its nonce remains available', () => {
    expect(isDefinitivelyDropped(false, 7, 7)).toBe(true)
    expect(isDefinitivelyDropped(false, 8, 7)).toBe(false)
  })

  it('never classifies a transaction still known by the node as dropped', () => {
    expect(isDefinitivelyDropped(true, 7, 7)).toBe(false)
  })
})
