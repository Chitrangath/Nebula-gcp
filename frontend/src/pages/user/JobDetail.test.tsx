import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import JobDetail from './JobDetail'
import { downloadJobResult, getJob, getJobResult } from '../../jobs/backend'

vi.mock('../../jobs/backend', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../jobs/backend')>()
  return { ...actual, getJob: vi.fn(), getJobResult: vi.fn(), downloadJobResult: vi.fn() }
})

const job = { id: 'job-1', chain_job_id: '0xabc', model_id: 'resnet50', status: 'completed', price_base_units: '50000', deadline: '2099-01-01T00:00:00Z', fingerprint: `0x${'11'.repeat(32)}`, created_at: '2026-01-01T00:00:00Z', attempt_count: 1, result_available: true, result_download_endpoint: '/v1/jobs/job-1/result', reconciliation_health: 'match', on_chain_state: 'Settled', proof_verification_status: 'valid', escrow_transaction: { hash: `0x${'aa'.repeat(32)}`, status: 'confirmed' }, settlement_transaction: { hash: `0x${'bb'.repeat(32)}`, status: 'confirmed' }, assignment_transaction: null, proof_transaction: null, refund_status: null, provider_payment_credit_status: 'completed' }

describe('JobDetail', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('shows the assigned GPU and provider wallet from authoritative job state', async () => {
    vi.mocked(getJob).mockResolvedValue({ ...job, result_available: false, assigned_node_id: 'node-5050', assigned_gpu_name: 'RTX 5050', assigned_provider_address: `0x${'33'.repeat(20)}` })
    render(<MemoryRouter initialEntries={['/user/jobs/job-1']}><Routes><Route path="/user/jobs/:id" element={<JobDetail />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('region', { name: 'Assigned provider' })).toHaveTextContent('RTX 5050')
    expect(screen.getByText('node-5050')).toBeInTheDocument()
    expect(screen.getByText(`0x${'33'.repeat(20)}`)).toBeInTheDocument()
  })

  it('shows lifecycle evidence, explorer links, and authorized result download', async () => {
    vi.mocked(getJob).mockResolvedValue(job)
    vi.mocked(getJobResult).mockResolvedValue({ model_id: 'resnet50', top_k: [{ index: 7, probability_hex: '0x1.0p-1' }] })
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

  it('shows the verified BERT result and all authoritative lifecycle stages', async () => {
    vi.mocked(getJob).mockResolvedValue({ ...job, model_id: 'bert-base' })
    vi.mocked(getJobResult).mockResolvedValue({
      model_id: 'bert-base',
      stars: 5,
      scores: [{ stars: 5, probability_hex: '0x1.0p-1' }],
    })

    render(<MemoryRouter initialEntries={['/user/jobs/job-1']}><Routes><Route path="/user/jobs/:id" element={<JobDetail />} /></Routes></MemoryRouter>)

    expect(await screen.findByRole('heading', { name: '5-star sentiment' })).toBeInTheDocument()
    expect(screen.getAllByText('50.0% confidence')).toHaveLength(2)
    expect(screen.getByLabelText('Job lifecycle')).toHaveTextContent('Escrow confirmed')
    expect(screen.getByLabelText('Job lifecycle')).toHaveTextContent('Proof verified')
    expect(screen.getByLabelText('Job lifecycle')).toHaveTextContent('Settled')
  })

  it('surfaces an open reconciliation incident without claiming a healthy result', async () => {
    vi.mocked(getJob).mockResolvedValue({ ...job, reconciliation_health: 'critical_incident', result_available: false })
    render(<MemoryRouter initialEntries={['/user/jobs/job-1']}><Routes><Route path="/user/jobs/:id" element={<JobDetail />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('reconciliation')
    expect(screen.queryByRole('button', { name: 'Download result' })).not.toBeInTheDocument()
    expect(getJobResult).not.toHaveBeenCalled()
  })

  it.each([
    ['failed', 'This job failed'],
    ['refunded', 'This job did not settle to a provider'],
  ])('shows the terminal %s recovery state without exposing result actions', async (status, message) => {
    vi.mocked(getJob).mockResolvedValue({ ...job, status, result_available: false })
    render(<MemoryRouter initialEntries={['/user/jobs/job-1']}><Routes><Route path="/user/jobs/:id" element={<JobDetail />} /></Routes></MemoryRouter>)

    expect(await screen.findByText(new RegExp(message, 'i'))).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Download result' })).not.toBeInTheDocument()
  })
})
