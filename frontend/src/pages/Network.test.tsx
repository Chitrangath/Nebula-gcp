import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getNetworkSnapshot, type NetworkSnapshot } from '../api/network'
import Network from './Network'

vi.mock('../api/network', () => ({ getNetworkSnapshot: vi.fn() }))

const snapshot = {
  observed_at: '2026-10-24T09:00:00Z',
  chain_id: 421614,
  heartbeat_ttl_seconds: 90,
  verifier_address: `0x${'38'.repeat(20)}`,
  viewer: { user_id: 'user-1', wallet_address: `0x${'10'.repeat(20)}`, role: 'ai_user' },
  nodes: [
    {
      id: 'node-3050', gpu_name: 'RTX 3050', vram_gb: 4, provider_wallet_address: `0x${'38'.repeat(20)}`,
      roles: ['gpu_provider', 'verifier'], status: 'online', last_heartbeat: '2026-10-24T08:59:45Z', heartbeat_age_seconds: 15,
      supported_models: ['resnet50', 'bert-base'],
      active_lease: { chain_job_id: `0x${'aa'.repeat(32)}`, model_id: 'bert-base', status: 'active', expires_at: '2026-10-24T09:05:00Z' },
      last_completed_job: { chain_job_id: `0x${'bb'.repeat(32)}`, model_id: 'resnet50', completed_at: '2026-10-24T08:58:00Z' },
    },
    {
      id: 'node-5050', gpu_name: 'RTX 5050', vram_gb: 8, provider_wallet_address: `0x${'50'.repeat(20)}`,
      roles: ['gpu_provider'], status: 'offline', last_heartbeat: '2026-10-24T08:50:00Z', heartbeat_age_seconds: 600,
      supported_models: ['resnet50'], active_lease: null, last_completed_job: null,
    },
  ],
} satisfies NetworkSnapshot

describe('Network', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('shows all demo devices, roles, live work, and the trust boundary', async () => {
    vi.mocked(getNetworkSnapshot).mockResolvedValue(snapshot)
    render(<Network />)

    expect(await screen.findByRole('heading', { name: 'Live compute network' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Connected browser' })).toHaveTextContent(snapshot.viewer.wallet_address)
    expect(screen.getByText('RTX 3050')).toBeInTheDocument()
    expect(screen.getByText('RTX 5050')).toBeInTheDocument()
    expect(screen.getAllByText('GPU provider')).toHaveLength(2)
    expect(screen.getAllByText('Verifier').length).toBeGreaterThan(0)
    expect(screen.getByText('BERT sentiment')).toBeInTheDocument()
    expect(screen.getByText(/active lease/i)).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: 'Last completed job' })).toHaveLength(2)
    expect(screen.getByRole('region', { name: 'Evidence boundaries' })).toHaveTextContent('Backend-observed')
    expect(screen.getByRole('region', { name: 'Evidence boundaries' })).toHaveTextContent('On-chain')
    expect(screen.queryByText(/api[_ -]?key/i)).not.toBeInTheDocument()
  })

  it('refreshes displayed node state on demand', async () => {
    vi.mocked(getNetworkSnapshot)
      .mockResolvedValueOnce(snapshot)
      .mockResolvedValueOnce({ ...snapshot, nodes: snapshot.nodes.map((node) => node.id === 'node-5050' ? { ...node, status: 'online', heartbeat_age_seconds: 2 } : node) })
    render(<Network />)

    expect(await screen.findByText('RTX 5050')).toBeInTheDocument()
    expect(within(screen.getByRole('article', { name: 'RTX 5050 network node' })).getByText(/offline/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Refresh network' }))
    expect(await within(screen.getByRole('article', { name: 'RTX 5050 network node' })).findByText(/online/i)).toBeInTheDocument()
    expect(getNetworkSnapshot).toHaveBeenCalledTimes(2)
  })
})
