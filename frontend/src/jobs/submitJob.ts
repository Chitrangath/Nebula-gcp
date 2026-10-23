export type Hex = `0x${string}`

export interface BackendJob {
  id: string
  chain_job_id: Hex
  fingerprint: Hex
  price_base_units: string
}

export interface JobBackend {
  createJob(request: JobSubmissionRequest, idempotencyKey: string, signal?: AbortSignal): Promise<BackendJob>
  confirmEscrow(jobId: string, transactionHash: Hex, signal?: AbortSignal): Promise<{ status: string }>
}

export interface FundingSnapshot {
  account: Hex
  token: Hex
  spender: Hex
  jobPrice: bigint
  allowance: bigint
  usdcBalance: bigint
  nativeBalance: bigint
  requiredNativeBalance: bigint
}

export interface TransactionReceipt {
  status: 'success' | 'reverted' | 'dropped'
  transactionHash: Hex
  replacement?: 'repriced' | 'replaced'
}

export interface ChainGateway {
  inspectFunding(signal?: AbortSignal): Promise<FundingSnapshot>
  approveExact(amount: bigint, signal?: AbortSignal): Promise<Hex>
  createJob(chainJobId: Hex, fingerprint: Hex, signal?: AbortSignal): Promise<Hex>
  waitForReceipt(transactionHash: Hex, signal?: AbortSignal): Promise<TransactionReceipt>
}

export interface JobSubmissionRequest {
  modelId: string
  input: File
  deadline: string
}

export interface SubmissionCheckpoint {
  idempotencyKey: string
  job?: BackendJob
  approvalTransactionHash?: Hex
  approvalConfirmed?: boolean
  escrowTransactionHash?: Hex
  finalEscrowTransactionHash?: Hex
}

export type SubmissionStage = 'uploading' | 'checking_funds' | 'approving' | 'creating_escrow' | 'confirming_escrow'

export class FundingError extends Error {
  constructor(readonly reason: 'price_mismatch' | 'insufficient_usdc' | 'insufficient_native') {
    super(reason === 'insufficient_usdc' ? 'Insufficient test USDC' : reason === 'insufficient_native' ? 'Insufficient test ETH for gas' : 'Backend and contract prices do not match')
    this.name = 'FundingError'
  }
}

export class TransactionError extends Error {
  constructor(readonly reason: 'approval_rejected' | 'approval_failed' | 'create_rejected' | 'dropped' | 'reverted' | 'receipt_uncertain') {
    super(`Escrow transaction failed: ${reason.replace(/_/g, ' ')}`)
    this.name = 'TransactionError'
  }
}

export class WalletIdentityError extends Error {
  constructor() {
    super('Reconnect and authenticate the wallet currently selected for funding')
    this.name = 'WalletIdentityError'
  }
}

export class FundingReviewChangedError extends Error {
  constructor() {
    super('Wallet funding details changed; review the updated signing summary')
    this.name = 'FundingReviewChangedError'
  }
}

function isKnownJourneyError(error: unknown): error is FundingError | TransactionError | WalletIdentityError {
  return error instanceof FundingError || error instanceof TransactionError || error instanceof WalletIdentityError
}

export interface SubmissionDependencies {
  backend: JobBackend
  chain: ChainGateway
  onStage?: (stage: SubmissionStage) => void
  signal?: AbortSignal
  authenticatedWallet?: Hex | null
  reviewedFunding?: FundingSnapshot
}

function newCheckpoint(): SubmissionCheckpoint {
  return { idempotencyKey: crypto.randomUUID() }
}

async function requireSuccessfulReceipt(
  chain: ChainGateway,
  hash: Hex,
  failureReason: 'approval_failed',
  signal?: AbortSignal,
): Promise<TransactionReceipt> {
  const receipt = await chain.waitForReceipt(hash, signal)
  if (receipt.status !== 'success') throw new TransactionError(failureReason)
  return receipt
}

export async function submitJob(
  request: JobSubmissionRequest,
  dependencies: SubmissionDependencies,
  checkpoint: SubmissionCheckpoint = newCheckpoint(),
): Promise<{ status: string; job: BackendJob; transactionHash: Hex; checkpoint: SubmissionCheckpoint }> {
  const { backend, chain, onStage, signal } = dependencies
  signal?.throwIfAborted()

  onStage?.('checking_funds')
  const funding = await chain.inspectFunding(signal)
  if (!dependencies.authenticatedWallet || funding.account.toLowerCase() !== dependencies.authenticatedWallet.toLowerCase()) {
    throw new WalletIdentityError()
  }
  if (dependencies.reviewedFunding) {
    const reviewed = dependencies.reviewedFunding
    const unchanged = reviewed.account.toLowerCase() === funding.account.toLowerCase() &&
      reviewed.token.toLowerCase() === funding.token.toLowerCase() && reviewed.spender.toLowerCase() === funding.spender.toLowerCase() &&
      reviewed.jobPrice === funding.jobPrice && reviewed.allowance === funding.allowance && reviewed.usdcBalance === funding.usdcBalance &&
      reviewed.nativeBalance === funding.nativeBalance && reviewed.requiredNativeBalance === funding.requiredNativeBalance
    if (!unchanged) throw new FundingReviewChangedError()
  }

  if (!checkpoint.job) {
    onStage?.('uploading')
    checkpoint.job = await backend.createJob(request, checkpoint.idempotencyKey, signal)
  }
  const job = checkpoint.job

  const backendPrice = BigInt(job.price_base_units)
  if (backendPrice !== funding.jobPrice) throw new FundingError('price_mismatch')
  if (funding.usdcBalance < funding.jobPrice) throw new FundingError('insufficient_usdc')
  if (funding.nativeBalance < funding.requiredNativeBalance) throw new FundingError('insufficient_native')

  if (funding.allowance < funding.jobPrice && !checkpoint.approvalConfirmed) {
    onStage?.('approving')
    if (!checkpoint.approvalTransactionHash) {
      try {
        checkpoint.approvalTransactionHash = await chain.approveExact(funding.jobPrice, signal)
      } catch (error) {
        if (isKnownJourneyError(error) || (error instanceof DOMException && error.name === 'AbortError')) throw error
        throw new TransactionError('approval_rejected')
      }
    }
    try {
      await requireSuccessfulReceipt(chain, checkpoint.approvalTransactionHash, 'approval_failed', signal)
      checkpoint.approvalConfirmed = true
    } catch (error) {
      if (error instanceof TransactionError && error.reason === 'approval_failed') checkpoint.approvalTransactionHash = undefined
      if (error instanceof DOMException && error.name === 'AbortError') throw error
      throw error instanceof TransactionError ? error : new TransactionError('receipt_uncertain')
    }
  }

  onStage?.('creating_escrow')
  if (!checkpoint.escrowTransactionHash) {
    try {
      checkpoint.escrowTransactionHash = await chain.createJob(job.chain_job_id, job.fingerprint, signal)
    } catch (error) {
      if (isKnownJourneyError(error) || (error instanceof DOMException && error.name === 'AbortError')) throw error
      throw new TransactionError('create_rejected')
    }
  }
  let receipt: TransactionReceipt
  try {
    receipt = await chain.waitForReceipt(checkpoint.escrowTransactionHash, signal)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new TransactionError('receipt_uncertain')
  }
  if (receipt.status !== 'success') {
    checkpoint.escrowTransactionHash = undefined
    throw new TransactionError(receipt.status)
  }
  checkpoint.finalEscrowTransactionHash = receipt.transactionHash

  onStage?.('confirming_escrow')
  const confirmation = await backend.confirmEscrow(job.id, receipt.transactionHash, signal)
  return { status: confirmation.status, job, transactionHash: receipt.transactionHash, checkpoint }
}
