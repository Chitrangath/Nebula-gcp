import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'

import { ApiProblemError, ApiUnavailableError } from '../../api/client'
import { getAuthenticatedWallet } from '../../api/session'
import { jobBackend, listSupportedModels, modelMimeTypes, type SupportedModel } from '../../jobs/backend'
import { createInjectedChainGateway } from '../../jobs/chain'
import { FundingError, FundingReviewChangedError, submitJob, TransactionError, WalletIdentityError, type ChainGateway, type FundingSnapshot, type Hex, type JobBackend, type SubmissionCheckpoint, type SubmissionStage } from '../../jobs/submitJob'

interface SubmitJobProps { models?: SupportedModel[]; backend?: JobBackend; chain?: ChainGateway; authenticatedWallet?: Hex | null }

const stageLabels: Record<SubmissionStage, string> = {
  uploading: 'Uploading and validating input…', checking_funds: 'Checking live price and wallet funds…',
  approving: 'Waiting for exact USDC approval…', creating_escrow: 'Waiting for escrow transaction…',
  confirming_escrow: 'Confirming escrow with Nebula…',
}

function safeError(error: unknown): string {
  if (error instanceof FundingError || error instanceof FundingReviewChangedError || error instanceof TransactionError || error instanceof WalletIdentityError || error instanceof ApiUnavailableError) return error.message
  if (error instanceof ApiProblemError) return `Nebula rejected the request: ${error.message}`
  if (error instanceof DOMException && error.name === 'AbortError') return 'Submission cancelled'
  return 'Job submission failed. Retry to continue safely from the last confirmed step.'
}

export default function SubmitJob({ models: suppliedModels, backend = jobBackend, chain: suppliedChain, authenticatedWallet }: SubmitJobProps) {
  const [models, setModels] = useState<SupportedModel[]>(suppliedModels ?? [])
  const [modelId, setModelId] = useState(suppliedModels?.[0]?.id ?? '')
  const [input, setInput] = useState<File | null>(null)
  const [stage, setStage] = useState<SubmissionStage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [complete, setComplete] = useState(false)
  const [review, setReview] = useState<FundingSnapshot | null>(null)
  const checkpoint = useRef<SubmissionCheckpoint | null>(null)
  const controller = useRef<AbortController | null>(null)
  const chain = useMemo(() => suppliedChain ?? (window.ethereum ? createInjectedChainGateway(window.ethereum) : null), [suppliedChain])
  const selectedModel = models.find((model) => model.id === modelId)

  useEffect(() => {
    if (suppliedModels) return
    const loadController = new AbortController()
    void listSupportedModels(loadController.signal).then((available) => available.filter((model) => model.id === 'resnet50')).then((available) => {
      setModels(available); setModelId(available[0]?.id ?? '')
    }).catch((caught) => { if (!loadController.signal.aborted) setError(safeError(caught)) })
    return () => loadController.abort()
  }, [suppliedModels])

  useEffect(() => () => controller.current?.abort(), [])

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!selectedModel || !input) { setError('Select the ResNet50 model and an input image'); return }
    if (selectedModel.max_input_size_mb && input.size > selectedModel.max_input_size_mb * 1024 * 1024) { setError(`Input is too large; maximum size is ${selectedModel.max_input_size_mb} MB`); return }
    if (!modelMimeTypes(selectedModel).includes(input.type)) { setError('Choose a supported JPEG or PNG input'); return }
    if (!chain) { setError('Connect an Arbitrum Sepolia wallet before funding a job'); return }
    const activeAuthenticatedWallet = authenticatedWallet === undefined ? getAuthenticatedWallet() : authenticatedWallet
    if (!review) {
      controller.current?.abort()
      const reviewController = new AbortController()
      controller.current = reviewController
      setStage('checking_funds')
      try {
        const funding = await chain.inspectFunding(reviewController.signal)
        if (!activeAuthenticatedWallet || funding.account.toLowerCase() !== activeAuthenticatedWallet.toLowerCase()) throw new WalletIdentityError()
        if (funding.usdcBalance < funding.jobPrice) throw new FundingError('insufficient_usdc')
        if (funding.nativeBalance < funding.requiredNativeBalance) throw new FundingError('insufficient_native')
        setReview(funding); setError(null)
      } catch (caught) { if (!reviewController.signal.aborted) setError(safeError(caught)) }
      finally { if (!reviewController.signal.aborted) setStage(null) }
      return
    }
    controller.current?.abort()
    const activeController = new AbortController()
    controller.current = activeController
    checkpoint.current ??= { idempotencyKey: crypto.randomUUID() }
    setError(null); setComplete(false)
    try {
      await submitJob({ modelId: selectedModel.id, input, deadline: new Date(Date.now() + 86_400_000).toISOString() }, {
        backend, chain, signal: activeController.signal, onStage: setStage, authenticatedWallet: activeAuthenticatedWallet, reviewedFunding: review,
      }, checkpoint.current)
      setComplete(true)
    } catch (caught) {
      if (!activeController.signal.aborted) {
        if (caught instanceof FundingReviewChangedError) setReview(null)
        setError(safeError(caught))
      }
    } finally {
      if (!activeController.signal.aborted) setStage(null)
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-2">Submit Job</h1>
      <p className="text-gray-600 mb-6">Upload one bounded ResNet50 image and fund its Arbitrum Sepolia escrow.</p>
      <form onSubmit={(event) => void handleSubmit(event)} className="space-y-5">
        <label className="block"><span className="block font-medium mb-1">Approved model</span>
          <select value={modelId} onChange={(event) => { setModelId(event.target.value); checkpoint.current = null; setReview(null) }} className="w-full border rounded p-2">
            {models.length === 0 ? <option value="">No ResNet50 model available</option> : null}
            {models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
          </select>
        </label>
        <label className="block"><span className="block font-medium mb-1">ResNet input</span>
          <input type="file" accept={selectedModel ? modelMimeTypes(selectedModel).join(',') : undefined} onChange={(event) => { setInput(event.target.files?.[0] ?? null); checkpoint.current = null; setReview(null) }} className="w-full border rounded p-2" />
          {selectedModel?.max_input_size_mb ? <span className="text-sm text-gray-600">Maximum {selectedModel.max_input_size_mb} MB</span> : null}
        </label>
        <div className="rounded border border-amber-300 bg-amber-50 p-4 text-sm">
          Nebula verifies the live contract price and wallet funds. If needed, your wallet requests an exact USDC approval, followed by one <code>createJob</code> escrow transaction. Only the confirmed transaction hash is sent to the backend.
        </div>
        {review ? <dl aria-label="Signing summary" className="rounded border p-4 text-sm break-all">
          <div><dt className="font-medium">Account</dt><dd>{review.account}</dd></div>
          <div><dt className="font-medium">Chain</dt><dd>Arbitrum Sepolia (421614)</dd></div>
          <div><dt className="font-medium">Token</dt><dd>{review.token}</dd></div>
          <div><dt className="font-medium">Spender</dt><dd>{review.spender}</dd></div>
          <div><dt className="font-medium">Exact escrow amount</dt><dd>{review.jobPrice.toString()} base units</dd></div>
          <div><dt className="font-medium">Estimated gas reserve</dt><dd>{review.requiredNativeBalance.toString()} wei</dd></div>
        </dl> : null}
        <button type="submit" disabled={stage !== null || complete || models.length === 0} className="bg-primary-600 text-white px-4 py-2 rounded-lg disabled:opacity-60">
          {stage ? stageLabels[stage] : error && checkpoint.current ? 'Retry submission' : review ? 'Confirm upload and sign' : 'Review funding'}
        </button>
      </form>
      {error ? <p role="alert" className="mt-4 text-red-700">{error}</p> : null}
      {complete ? <p role="status" className="mt-4 text-green-700">Escrow confirmed. Your job is ready for assignment.</p> : null}
    </div>
  )
}
