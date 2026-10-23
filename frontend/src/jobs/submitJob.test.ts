import { describe, expect, it, vi } from 'vitest'

import {
  FundingError,
  FundingReviewChangedError,
  TransactionError,
  WalletIdentityError,
  submitJob,
  type ChainGateway,
  type JobBackend,
  type SubmissionCheckpoint,
} from './submitJob'
import { WrongChainError } from '../wallet/wallet'

const backendJob = {
  id: '123e4567-e89b-12d3-a456-426614174000',
  chain_job_id: `0x${'12'.repeat(16)}${'00'.repeat(16)}`,
  fingerprint: `0x${'34'.repeat(32)}`,
  price_base_units: '50000',
}
const account = `0x${'56'.repeat(20)}` as const
const funding = { account, token: `0x${'78'.repeat(20)}` as const, spender: `0x${'90'.repeat(20)}` as const, jobPrice: 50_000n, allowance: 0n, usdcBalance: 100_000n, nativeBalance: 1n, requiredNativeBalance: 1n }

function backend(): JobBackend {
  return {
    createJob: vi.fn().mockResolvedValue(backendJob),
    confirmEscrow: vi.fn().mockResolvedValue({ status: 'escrow_confirmed' }),
  }
}

function chain(overrides: Partial<ChainGateway> = {}): ChainGateway {
  return {
    inspectFunding: vi.fn().mockResolvedValue(funding),
    approveExact: vi.fn().mockResolvedValue(`0x${'a1'.repeat(32)}`),
    createJob: vi.fn().mockResolvedValue(`0x${'b2'.repeat(32)}`),
    waitForReceipt: vi.fn().mockImplementation(async (hash) => ({ status: 'success', transactionHash: hash })),
    ...overrides,
  }
}

const request = {
  modelId: 'resnet50',
  input: new File(['image'], 'input.png', { type: 'image/png' }),
  deadline: '2099-01-01T00:00:00.000Z',
}

describe('AI-user upload and escrow journey', () => {
  it('rejects a funding wallet that differs from the authenticated AI user before upload', async () => {
    const api = backend()
    const wallet = chain()

    await expect(submitJob(request, { backend: api, chain: wallet, authenticatedWallet: `0x${'99'.repeat(20)}` })).rejects.toBeInstanceOf(WalletIdentityError)
    expect(api.createJob).not.toHaveBeenCalled()
  })

  it('requires a new review when material funding facts change before signing', async () => {
    const wallet = chain()
    await expect(submitJob(request, {
      backend: backend(), chain: wallet, authenticatedWallet: account,
      reviewedFunding: { ...funding, allowance: 50_000n },
    })).rejects.toBeInstanceOf(FundingReviewChangedError)
  })

  it('uploads once, approves the exact live price, creates escrow, and confirms only its final hash', async () => {
    const api = backend()
    const wallet = chain()

    const result = await submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account })

    expect(api.createJob).toHaveBeenCalledOnce()
    expect(wallet.approveExact).toHaveBeenCalledWith(50_000n, undefined)
    expect(wallet.createJob).toHaveBeenCalledWith(backendJob.chain_job_id, backendJob.fingerprint, undefined)
    expect(api.confirmEscrow).toHaveBeenCalledWith(backendJob.id, `0x${'b2'.repeat(32)}`, undefined)
    expect(result.status).toBe('escrow_confirmed')
  })

  it.each([
    ['USDC', { usdcBalance: 49_999n, nativeBalance: 1n }],
    ['test ETH', { usdcBalance: 100_000n, nativeBalance: 0n }],
  ])('stops before signing when %s funding is insufficient', async (_label, balances) => {
    const wallet = chain({
      inspectFunding: vi.fn().mockResolvedValue({ ...funding, ...balances }),
    })

    await expect(submitJob(request, { backend: backend(), chain: wallet, authenticatedWallet: account })).rejects.toBeInstanceOf(FundingError)
    expect(wallet.approveExact).not.toHaveBeenCalled()
    expect(wallet.createJob).not.toHaveBeenCalled()
  })

  it('surfaces approval rejection without creating escrow', async () => {
    const wallet = chain({ approveExact: vi.fn().mockRejectedValue(new Error('provider internals')) })

    await expect(submitJob(request, { backend: backend(), chain: wallet, authenticatedWallet: account })).rejects.toEqual(
      new TransactionError('approval_rejected'),
    )
    expect(wallet.createJob).not.toHaveBeenCalled()
  })

  it('stops on the wrong chain before approval or escrow', async () => {
    const wallet = chain({ inspectFunding: vi.fn().mockRejectedValue(new WrongChainError(1)) })

    await expect(submitJob(request, { backend: backend(), chain: wallet, authenticatedWallet: account })).rejects.toEqual(new WrongChainError(1))
    expect(wallet.approveExact).not.toHaveBeenCalled()
    expect(wallet.createJob).not.toHaveBeenCalled()
  })

  it('does not create escrow after a reverted approval', async () => {
    const wallet = chain({
      waitForReceipt: vi.fn().mockResolvedValue({ status: 'reverted', transactionHash: `0x${'a1'.repeat(32)}` }),
    })

    await expect(submitJob(request, { backend: backend(), chain: wallet, authenticatedWallet: account })).rejects.toEqual(new TransactionError('approval_failed'))
    expect(wallet.createJob).not.toHaveBeenCalled()
  })

  it('surfaces createJob rejection without backend confirmation', async () => {
    const api = backend()
    const wallet = chain({ createJob: vi.fn().mockRejectedValue(new Error('user rejected')) })

    await expect(submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account })).rejects.toEqual(new TransactionError('create_rejected'))
    expect(api.confirmEscrow).not.toHaveBeenCalled()
  })

  it('uses the replacement hash when a transaction is repriced', async () => {
    const replacement = `0x${'cd'.repeat(32)}` as const
    const wallet = chain({
      waitForReceipt: vi.fn()
        .mockResolvedValueOnce({ status: 'success', transactionHash: `0x${'a1'.repeat(32)}` })
        .mockResolvedValueOnce({ status: 'success', transactionHash: replacement, replacement: 'repriced' }),
    })
    const api = backend()

    await submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account })

    expect(api.confirmEscrow).toHaveBeenCalledWith(backendJob.id, replacement, undefined)
  })

  it.each(['dropped', 'reverted'] as const)('does not confirm a %s escrow receipt', async (status) => {
    const wallet = chain({
      waitForReceipt: vi.fn()
        .mockResolvedValueOnce({ status: 'success', transactionHash: `0x${'a1'.repeat(32)}` })
        .mockResolvedValueOnce({ status, transactionHash: `0x${'b2'.repeat(32)}` }),
    })
    const api = backend()

    await expect(submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account })).rejects.toEqual(new TransactionError(status))
    expect(api.confirmEscrow).not.toHaveBeenCalled()
  })

  it('retries from its checkpoint without duplicate upload, approval, or createJob submission', async () => {
    const checkpoint: SubmissionCheckpoint = { idempotencyKey: 'fixed-key' }
    const api = backend()
    vi.mocked(api.confirmEscrow).mockRejectedValueOnce(new Error('backend unavailable'))
    const wallet = chain()

    await expect(submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account }, checkpoint)).rejects.toThrow()
    await submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account }, checkpoint)

    expect(api.createJob).toHaveBeenCalledOnce()
    expect(wallet.approveExact).toHaveBeenCalledOnce()
    expect(wallet.createJob).toHaveBeenCalledOnce()
    expect(api.confirmEscrow).toHaveBeenCalledTimes(2)
  })

  it('retains a broadcast escrow hash across an uncertain receipt timeout', async () => {
    const checkpoint: SubmissionCheckpoint = { idempotencyKey: 'fixed-key' }
    const api = backend()
    const wallet = chain({
      waitForReceipt: vi.fn()
        .mockResolvedValueOnce({ status: 'success', transactionHash: `0x${'a1'.repeat(32)}` })
        .mockRejectedValueOnce(new Error('RPC timeout'))
        .mockResolvedValueOnce({ status: 'success', transactionHash: `0x${'b2'.repeat(32)}` }),
    })

    await expect(submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account }, checkpoint)).rejects.toEqual(new TransactionError('receipt_uncertain'))
    await submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account }, checkpoint)

    expect(wallet.createJob).toHaveBeenCalledOnce()
    expect(wallet.waitForReceipt).toHaveBeenLastCalledWith(`0x${'b2'.repeat(32)}`, undefined)
  })

  it('retains a broadcast approval hash across an uncertain receipt timeout', async () => {
    const checkpoint: SubmissionCheckpoint = { idempotencyKey: 'fixed-key' }
    const api = backend()
    const wallet = chain({
      waitForReceipt: vi.fn()
        .mockRejectedValueOnce(new Error('RPC timeout'))
        .mockResolvedValueOnce({ status: 'success', transactionHash: `0x${'a1'.repeat(32)}` })
        .mockResolvedValueOnce({ status: 'success', transactionHash: `0x${'b2'.repeat(32)}` }),
    })

    await expect(submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account }, checkpoint)).rejects.toEqual(new TransactionError('receipt_uncertain'))
    await submitJob(request, { backend: api, chain: wallet, authenticatedWallet: account }, checkpoint)

    expect(wallet.approveExact).toHaveBeenCalledOnce()
    expect(wallet.createJob).toHaveBeenCalledOnce()
  })
})
