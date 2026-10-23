import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import JobDetail from './JobDetail'
import { downloadJobResult, getJob } from '../../jobs/backend'

vi.mock('../../jobs/backend', () => ({ getJob: vi.fn(), downloadJobResult: vi.fn() }))

const job = { id: 'job-1', chain_job_id: '0xabc', model_id: 'resnet50', status: 'completed', price_base_units: '50000', deadline: '2099-01-01T00:00:00Z', fingerprint: `0x${'11'.repeat(32)}`, created_at: '2026-01-01T00:00:00Z', attempt_count: 1, result_available: true, result_download_endpoint: '/v1/jobs/job-1/result', reconciliation_health: 'match', on_chain_state: 'Settled', proof_verification_status: 'valid', escrow_transaction: { hash: `0x${'aa'.repeat(32)}`, status: 'confirmed' }, settlement_transaction: { hash: `0x${'bb'.repeat(32)}`, status: 'confirmed' }, assignment_transaction: null, proof_transaction: null, refund_status: null, provider_payment_credit_status: 'completed' }

describe('JobDetail', () => {
  afterEach(cleanup)

  it('shows lifecycle evidence, explorer links, and authorized result download', async () => {
    vi.mocked(getJob).mockResolvedValue(job)
    vi.mocked(downloadJobResult).mockResolvedValue(new Blob(['result'], { type: 'application/octet-stream' }))
    const createUrl = vi.fn().mockReturnValue('blob:result')
    Object.defineProperty(URL, 'createObjectURL', { value: createUrl, configurable: true })
    render(<MemoryRouter initialEntries={['/user/jobs/job-1']}><Routes><Route path="/user/jobs/:id" element={<JobDetail />} /></Routes></MemoryRouter>)

    expect(await screen.findByText('resnet50')).toBeInTheDocument()
    expect(screen.getByText('valid')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /escrow transaction/i })).toHaveAttribute('href', expect.stringContaining(job.escrow_transaction.hash))
    await userEvent.click(screen.getByRole('button', { name: 'Download result' }))
    expect(downloadJobResult).toHaveBeenCalledWith('job-1', expect.any(AbortSignal))
    expect(createUrl).toHaveBeenCalledWith(expect.any(Blob))
  })

  it('surfaces an open reconciliation incident without claiming a healthy result', async () => {
    vi.mocked(getJob).mockResolvedValue({ ...job, reconciliation_health: 'critical_incident', result_available: false })
    render(<MemoryRouter initialEntries={['/user/jobs/job-1']}><Routes><Route path="/user/jobs/:id" element={<JobDetail />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('reconciliation')
    expect(screen.queryByRole('button', { name: 'Download result' })).not.toBeInTheDocument()
  })
})
