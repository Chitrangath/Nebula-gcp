import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import type { SupportedModel } from '../../jobs/backend'
import type { ChainGateway, JobBackend } from '../../jobs/submitJob'
import SubmitJob from './SubmitJob'
import { setAuthenticatedWallet } from '../../api/session'

const account = `0x${'56'.repeat(20)}` as const
const model: SupportedModel = { id: 'resnet50', name: 'ResNet50', input_type: 'image', supported_formats: ['png', 'jpg', 'jpeg'], max_input_size_mb: 25, price_base_units: '50000' }
const bertModel: SupportedModel = { id: 'bert-base', name: 'BERT sentiment', input_type: 'text', supported_formats: ['txt'], max_input_size_mb: 1, price_base_units: '50000' }

function dependencies() {
  const backend: JobBackend = {
    createJob: vi.fn().mockResolvedValue({ id: '123e4567-e89b-12d3-a456-426614174000', chain_job_id: `0x${'12'.repeat(16)}${'00'.repeat(16)}`, fingerprint: `0x${'34'.repeat(32)}`, price_base_units: '50000' }),
    confirmEscrow: vi.fn().mockResolvedValue({ status: 'escrow_confirmed' }),
  }
  const chain: ChainGateway = {
    inspectFunding: vi.fn().mockResolvedValue({ account, token: `0x${'78'.repeat(20)}`, spender: `0x${'90'.repeat(20)}`, jobPrice: 50_000n, allowance: 50_000n, usdcBalance: 50_000n, nativeBalance: 1n, requiredNativeBalance: 1n }),
    approveExact: vi.fn(),
    createJob: vi.fn().mockResolvedValue(`0x${'ab'.repeat(32)}`),
    waitForReceipt: vi.fn().mockImplementation(async (hash) => ({ status: 'success', transactionHash: hash })),
  }
  return { backend, chain }
}

describe('SubmitJob', () => {
  afterEach(() => { cleanup(); delete window.ethereum })

  it('keeps the submission page usable when the payment contract is not configured', async () => {
    window.ethereum = { request: vi.fn() }
    render(<MemoryRouter><SubmitJob models={[model]} /></MemoryRouter>)

    expect(screen.getByRole('heading', { name: 'Submit an inference job' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Nebula payment contract is not configured')
    expect(screen.getByRole('button', { name: 'Review funding' })).toBeDisabled()
  })

  it('shows the signing summary and completes the ResNet escrow journey', async () => {
    const deps = dependencies()
    render(<MemoryRouter><SubmitJob models={[model]} backend={deps.backend} chain={deps.chain} authenticatedWallet={account} /></MemoryRouter>)
    expect(screen.getByText(/exact USDC approval/i)).toBeInTheDocument()
    expect(screen.getByRole('complementary', { name: 'Submission overview' })).toHaveTextContent('50,000 base units')
    await userEvent.upload(screen.getByLabelText(/^ResNet input/), new File(['image'], 'cat.png', { type: 'image/png' }))
    await userEvent.click(screen.getByRole('button', { name: 'Review funding' }))
    expect(screen.getByLabelText('Signing summary')).toHaveTextContent(account)
    expect(screen.getByLabelText('Signing summary')).toHaveTextContent('50000 base units')
    await userEvent.click(screen.getByRole('button', { name: 'Confirm upload and sign' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Escrow confirmed')
    expect(deps.backend.createJob).toHaveBeenCalledOnce()
    expect(deps.backend.confirmEscrow).toHaveBeenCalledOnce()
  })

  it('rejects an oversized input before upload or wallet signing', async () => {
    const deps = dependencies()
    render(<MemoryRouter><SubmitJob models={[{ ...model, max_input_size_mb: 0.000001 }]} backend={deps.backend} chain={deps.chain} authenticatedWallet={account} /></MemoryRouter>)
    await userEvent.upload(screen.getByLabelText(/^ResNet input/), new File(['too large'], 'cat.png', { type: 'image/png' }))
    await userEvent.click(screen.getByRole('button', { name: 'Review funding' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('too large')
    expect(deps.backend.createJob).not.toHaveBeenCalled()
    expect(deps.chain.createJob).not.toHaveBeenCalled()
  })

  it('reads a wallet authenticated after the page was already rendered', async () => {
    const deps = dependencies()
    render(<MemoryRouter><SubmitJob models={[model]} backend={deps.backend} chain={deps.chain} /></MemoryRouter>)
    setAuthenticatedWallet(account)
    await userEvent.upload(screen.getByLabelText(/^ResNet input/), new File(['image'], 'cat.png', { type: 'image/png' }))

    await userEvent.click(screen.getByRole('button', { name: 'Review funding' }))

    expect(await screen.findByLabelText('Signing summary')).toHaveTextContent(account)
  })

  it('submits bounded BERT text as an exact UTF-8 input file', async () => {
    const deps = dependencies()
    render(<MemoryRouter><SubmitJob models={[model, bertModel]} backend={deps.backend} chain={deps.chain} authenticatedWallet={account} /></MemoryRouter>)

    await userEvent.selectOptions(screen.getByLabelText('Approved model'), 'bert-base')
    await userEvent.type(screen.getByLabelText('Text to analyse'), 'This project works beautifully.')
    await userEvent.click(screen.getByRole('button', { name: 'Review funding' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm upload and sign' }))

    expect(await screen.findByRole('status')).toHaveTextContent('ready for assignment')
    const request = vi.mocked(deps.backend.createJob).mock.calls[0][0]
    expect(request.modelId).toBe('bert-base')
    expect(request.input.name).toBe('input.txt')
    expect(request.input.type).toBe('text/plain')
    const text = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.addEventListener('load', () => resolve(String(reader.result)))
      reader.addEventListener('error', () => reject(reader.error))
      reader.readAsText(request.input)
    })
    expect(text).toBe('This project works beautifully.')
    expect(screen.getByRole('link', { name: 'Follow job progress' })).toHaveAttribute(
      'href',
      '/user/jobs/123e4567-e89b-12d3-a456-426614174000',
    )
  })

  it('shows a recoverable inline error for empty BERT text', async () => {
    const deps = dependencies()
    render(<MemoryRouter><SubmitJob models={[bertModel]} backend={deps.backend} chain={deps.chain} authenticatedWallet={account} /></MemoryRouter>)

    await userEvent.click(screen.getByRole('button', { name: 'Review funding' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter text for BERT sentiment analysis')
    expect(deps.chain.inspectFunding).not.toHaveBeenCalled()
  })

  it('rejects BERT text beyond the executable token-safe bound before funding', async () => {
    const deps = dependencies()
    render(<MemoryRouter><SubmitJob models={[bertModel]} backend={deps.backend} chain={deps.chain} authenticatedWallet={account} /></MemoryRouter>)

    await userEvent.type(screen.getByLabelText('Text to analyse'), 'a'.repeat(511))
    await userEvent.click(screen.getByRole('button', { name: 'Review funding' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('510 characters')
    expect(deps.chain.inspectFunding).not.toHaveBeenCalled()
    expect(deps.backend.createJob).not.toHaveBeenCalled()
  })
})
