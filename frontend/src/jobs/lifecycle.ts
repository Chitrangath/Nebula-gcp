import { useEffect, useState } from 'react'

import type { components } from '../api/schema'
import { getJob } from './backend'

export type Job = components['schemas']['JobResponse']

export function isTerminalJob(status: string): boolean {
  return ['completed', 'failed', 'refunded'].includes(status)
}

export function nextPollDelay(attempt: number, visible: boolean): number {
  if (!visible) return 30_000
  if (attempt === 0) return 5000
  if (attempt <= 2) return 10_000
  return 30_000
}

export function useJobLifecycle(jobId: string | undefined): { job: Job | null; loading: boolean; error: Error | null; retry: () => void } {
  const [job, setJob] = useState<Job | null>(null)
  const [loading, setLoading] = useState(Boolean(jobId))
  const [error, setError] = useState<Error | null>(null)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    setJob(null); setError(null); setLoading(Boolean(jobId))
    if (!jobId) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    let failureAttempt = 0
    let stopped = false
    let inFlight = false
    const poll = async () => {
      if (inFlight || stopped) return
      inFlight = true
      try {
        const current = await getJob(jobId, controller.signal)
        if (stopped) return
        setJob(current); setError(null); setLoading(false); failureAttempt = 0
        if (isTerminalJob(current.status) && current.reconciliation_health !== 'critical_incident') return
        if (document.visibilityState === 'hidden') return
        timer = setTimeout(() => void poll(), nextPollDelay(failureAttempt++, true))
      } catch (caught) {
        if (stopped || controller.signal.aborted) return
        setError(caught instanceof Error ? caught : new Error('Unable to load job'))
        setLoading(false)
        if (document.visibilityState !== 'hidden') timer = setTimeout(() => void poll(), nextPollDelay(failureAttempt++, true))
      } finally {
        inFlight = false
      }
    }
    const onVisibility = () => { if (document.visibilityState === 'visible' && !stopped) { if (timer) clearTimeout(timer); void poll() } }
    document.addEventListener('visibilitychange', onVisibility)
    void poll()
    return () => { stopped = true; controller.abort(); if (timer) clearTimeout(timer); document.removeEventListener('visibilitychange', onVisibility) }
  }, [jobId, revision])

  return { job, loading, error, retry: () => { setError(null); setLoading(true); setRevision((value) => value + 1) } }
}
