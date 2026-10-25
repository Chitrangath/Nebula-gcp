import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import UserDashboard from './Dashboard'
import { listJobs } from '../../jobs/backend'

vi.mock('../../jobs/backend', () => ({ listJobs: vi.fn() }))

const job = { id: 'job-1', chain_job_id: '0xabc', chain_id: 421614, model_id: 'resnet50', status: 'running', price_base_units: '50000', deadline: '2099-01-01T00:00:00Z', fingerprint: null, created_at: '2026-01-01T00:00:00Z', attempt_count: 1, result_available: false, reconciliation_health: 'match' }

describe('UserDashboard', () => {
  afterEach(cleanup)

  it('lists authoritative job state and links to detail', async () => {
    vi.mocked(listJobs).mockResolvedValue([job])
    render(<MemoryRouter><UserDashboard /></MemoryRouter>)
    expect(await screen.findByText('running')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ResNet50 image classification' })).toHaveAttribute('href', '/user/jobs/job-1')
    expect(screen.getByText('Active jobs')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Submit a job' })).toHaveAttribute('href', '/user/submit')
  })
})
