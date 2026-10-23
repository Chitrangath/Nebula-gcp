import { describe, expect, it } from 'vitest'

import { isTerminalJob, nextPollDelay } from './lifecycle'

describe('job lifecycle polling policy', () => {
  it('backs off while visible and slows further in a hidden tab', () => {
    expect(nextPollDelay(0, true)).toBe(5000)
    expect(nextPollDelay(2, true)).toBe(10000)
    expect(nextPollDelay(2, false)).toBe(30000)
    expect(nextPollDelay(99, true)).toBe(30000)
  })

  it.each(['completed', 'failed', 'refunded'])('stops polling terminal status %s', (status) => {
    expect(isTerminalJob(status)).toBe(true)
  })

  it('keeps active and reconciliation states polling', () => {
    expect(isTerminalJob('running')).toBe(false)
    expect(isTerminalJob('completed_with_incident')).toBe(false)
  })
})
