import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { getProviderDashboard } from '../../api/nodes'
import { setAuthenticatedWallet } from '../../api/session'
import ProviderDashboard from './Dashboard'

vi.mock('../../api/nodes', () => ({ getProviderDashboard: vi.fn() }))

const wallet = `0x${'34'.repeat(20)}` as const
const dashboard = {
  nodes: [{
    id: 'node-1', gpu_name: 'RTX 3050', vram_gb: 4, status: 'online',
    last_heartbeat: '2026-10-24T08:00:00Z', active_leases: 1,
    worker_signer_address: `0x${'56'.repeat(20)}`, supported_models: ['resnet50', 'bert-base'],
    active_lease: { job_id: 'job-1', model_id: 'bert-base', status: 'active', expires_at: '2026-10-24T09:00:00Z' },
    recent_jobs: [{ job_id: 'job-0', model_id: 'resnet50', status: 'completed', completed_at: '2026-10-24T07:00:00Z' }],
  }],
  earnings: {
    provider_id: 'provider-1', total_credited_base_units: '50000', total_withdrawn_base_units: '0',
    pending_withdrawal_base_units: '50000', pending_withdrawal_status: 'current',
    credits: [{ job_id: 'job-0', amount_base_units: '50000', status: 'credited', blockchain_tx_hash: `0x${'ab'.repeat(32)}`, withdrawal_tx_hash: null, credited_at: '2026-10-24T07:01:00Z', withdrawn_at: null }],
  },
}

describe('ProviderDashboard', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('shows provider identity, capabilities, active work, completed work, and earnings', async () => {
    setAuthenticatedWallet(wallet)
    vi.mocked(getProviderDashboard).mockResolvedValue(dashboard)

    render(<MemoryRouter><ProviderDashboard /></MemoryRouter>)

    expect(await screen.findByText('RTX 3050')).toBeInTheDocument()
    expect(screen.getByText(wallet)).toBeInTheDocument()
    expect(screen.getByText('BERT sentiment')).toBeInTheDocument()
    expect(screen.getByText('Active · BERT sentiment')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Completed jobs & credits' })).toBeInTheDocument()
    expect(screen.getAllByText('50,000 base units')).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'View settlement transaction' })).toHaveAttribute(
      'href',
      `https://sepolia.arbiscan.io/tx/0x${'ab'.repeat(32)}`,
    )
    expect(screen.queryByText(/api[_ -]?key/i)).not.toBeInTheDocument()
  })

  it('provides an explicit retry when provider data cannot be loaded', async () => {
    vi.mocked(getProviderDashboard)
      .mockRejectedValueOnce(new Error('Backend unavailable'))
      .mockResolvedValueOnce(dashboard)

    render(<MemoryRouter><ProviderDashboard /></MemoryRouter>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable')
    await userEvent.click(screen.getByRole('button', { name: 'Retry dashboard' }))
    expect(await screen.findByText('RTX 3050')).toBeInTheDocument()
    expect(getProviderDashboard).toHaveBeenCalledTimes(2)
  })
})
