import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiProblemError, ApiUnavailableError } from '../../api/client'
import { getAuthenticatedWallet } from '../../api/session'
import { jobBackend, listSupportedModels, modelMimeTypes, type SupportedModel } from '../../jobs/backend'
import { createInjectedChainGateway } from '../../jobs/chain'
import { FundingError, FundingReviewChangedError, submitJob, TransactionError, WalletIdentityError, type ChainGateway, type FundingSnapshot, type Hex, type JobBackend, type SubmissionCheckpoint, type SubmissionStage } from '../../jobs/submitJob'

interface SubmitJobProps { models?: SupportedModel[]; backend?: JobBackend; chain?: ChainGateway; authenticatedWallet?: Hex | null }

const MAX_BERT_INPUT_CODE_POINTS = 510

const stageLabels: Record<SubmissionStage, string> = {
  uploading: 'Uploading and validating input…', checking_funds: 'Checking live price and wallet funds…',
  approving: 'Waiting for exact USDC approval…', creating_escrow: 'Waiting for escrow transaction…',
  confirming_escrow: 'Confirming escrow with Nebula…',
}

function imageInputGuidance(model: SupportedModel): string {
  const formats = model.supported_formats.map((format) => `.${format.replace(/^\./, '').toLowerCase()}`).join(', ')
  const size = model.max_input_size_mb ? ` Maximum size: ${model.max_input_size_mb} MB.` : ''
  return `Use a valid ${formats} image with matching file extension and MIME type.${size} Image dimensions must be between 1 and 16,384 pixels on each side.`
}

function explainInputProblem(detail: string, model: SupportedModel): string {
  const normalized = detail.toLowerCase()
  if (model.input_type !== 'image') return `BERT input rejected: ${detail}. Use non-empty UTF-8 text of at most 510 characters.`
  if (normalized.includes('size limit')) return `Image rejected: ${detail}. ${imageInputGuidance(model)}`
  if (normalized.includes('dimension')) return `Image rejected: ${detail}. Use width and height from 1 to 16,384 pixels.`
  if (normalized.includes('mime type') || normalized.includes('extension') || normalized.includes('magic bytes') || normalized.includes('malformed')) {
    return `Image rejected: ${detail}. Re-save or export the image as a real JPEG or PNG, then upload it with the matching .jpg, .jpeg, or .png extension.`
  }
  return `Nebula rejected the input: ${detail}. ${imageInputGuidance(model)}`
}

function safeError(error: unknown, model?: SupportedModel): string {
  if (error instanceof FundingError || error instanceof FundingReviewChangedError || error instanceof TransactionError || error instanceof WalletIdentityError || error instanceof ApiUnavailableError) return error.message
  if (error instanceof ApiProblemError) {
    if (error.detail && model && (error.status === 400 || error.status === 413 || error.status === 422)) return explainInputProblem(error.detail, model)
    return `Nebula rejected the request: ${error.detail ?? error.message}`
  }
  if (error instanceof DOMException && error.name === 'AbortError') return 'Submission cancelled'
  return 'Job submission failed. Retry to continue safely from the last confirmed step.'
}

function listedPrice(value: string): string {
  try { return `${BigInt(value).toLocaleString()} base units` } catch { return 'Unavailable' }
}

export default function SubmitJob({ models: suppliedModels, backend = jobBackend, chain: suppliedChain, authenticatedWallet }: SubmitJobProps) {
  const [models, setModels] = useState<SupportedModel[]>(suppliedModels ?? [])
  const [modelId, setModelId] = useState(suppliedModels?.[0]?.id ?? '')
  const [input, setInput] = useState<File | null>(null)
  const [textInput, setTextInput] = useState('')
  const [stage, setStage] = useState<SubmissionStage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submittedJobId, setSubmittedJobId] = useState<string | null>(null)
  const [review, setReview] = useState<FundingSnapshot | null>(null)
  const checkpoint = useRef<SubmissionCheckpoint | null>(null)
  const controller = useRef<AbortController | null>(null)
  const [chain, chainError] = useMemo((): [ChainGateway | null, string | null] => {
    if (suppliedChain) return [suppliedChain, null]
    if (!window.ethereum) return [null, null]
    try { return [createInjectedChainGateway(window.ethereum), null] }
    catch (caught) { return [null, caught instanceof Error ? caught.message : 'Payment contract configuration is unavailable'] }
  }, [suppliedChain])
  const selectedModel = models.find((model) => model.id === modelId)

  useEffect(() => {
    if (suppliedModels) return
    const loadController = new AbortController()
    void listSupportedModels(loadController.signal).then((available) => available.filter((model) => ['resnet50', 'bert-base'].includes(model.id))).then((available) => {
      setModels(available); setModelId(available[0]?.id ?? '')
    }).catch((caught) => { if (!loadController.signal.aborted) setError(safeError(caught)) })
    return () => loadController.abort()
  }, [suppliedModels])

  useEffect(() => () => controller.current?.abort(), [])

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!selectedModel) { setError('Select an approved model'); return }
    let submissionInput = input
    if (selectedModel.input_type === 'text') {
      const textBytes = new TextEncoder().encode(textInput)
      if (!textInput.trim()) { setError('Enter text for BERT sentiment analysis, then try again'); return }
      if (textInput.includes('\0')) { setError('Text cannot contain null characters'); return }
      if (Array.from(textInput).length > MAX_BERT_INPUT_CODE_POINTS) { setError('BERT text is too long; enter at most 510 characters'); return }
      if (textBytes.byteLength > 65_536) { setError('Text is too large; maximum size is 64 KiB'); return }
      submissionInput = new File([textBytes], 'input.txt', { type: 'text/plain' })
    }
    if (!submissionInput) { setError('Choose a JPEG or PNG image, then try again'); return }
    if (selectedModel.max_input_size_mb && submissionInput.size > selectedModel.max_input_size_mb * 1024 * 1024) { setError(`Input is too large; maximum size is ${selectedModel.max_input_size_mb} MB`); return }
    if (!modelMimeTypes(selectedModel).includes(submissionInput.type)) {
      setError(selectedModel.input_type === 'text' ? 'Choose a supported text input' : `Image format not supported. ${imageInputGuidance(selectedModel)}`)
      return
    }
    if (!chain) { setError(chainError ?? 'Connect an Arbitrum Sepolia wallet before funding a job'); return }
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
    setError(null); setSubmittedJobId(null)
    try {
      const submission = await submitJob({ modelId: selectedModel.id, input: submissionInput, deadline: new Date(Date.now() + 86_400_000).toISOString() }, {
        backend, chain, signal: activeController.signal, onStage: setStage, authenticatedWallet: activeAuthenticatedWallet, reviewedFunding: review,
      }, checkpoint.current)
      setSubmittedJobId(submission.job.id)
    } catch (caught) {
      if (!activeController.signal.aborted) {
        if (caught instanceof FundingReviewChangedError) setReview(null)
        setError(safeError(caught, selectedModel))
      }
    } finally {
      if (!activeController.signal.aborted) setStage(null)
    }
  }

  return (
    <div className="nebula-form-page">
      <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-primary-700">AI user workspace</p>
      <h1 className="text-3xl font-bold tracking-tight">Submit an inference job</h1>
      <p className="mb-8 mt-2 text-gray-600">Choose a backend-approved model, add its input, then review and fund the Arbitrum Sepolia escrow.</p>
      <div className="nebula-submit-grid">
      <form onSubmit={(event) => void handleSubmit(event)} className="space-y-6 rounded-xl border border-gray-200 bg-white p-5 sm:p-6">
        <label className="block"><span className="mb-2 block font-medium">Approved model</span>
          <select value={modelId} onChange={(event) => { setModelId(event.target.value); setInput(null); setTextInput(''); setError(null); setSubmittedJobId(null); checkpoint.current = null; setReview(null) }} className="min-h-11 w-full rounded-lg border border-gray-300 bg-white p-3 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-200">
            {models.length === 0 ? <option value="">No approved model available</option> : null}
            {models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
          </select>
        </label>
        {selectedModel?.input_type === 'text' ? <div><label htmlFor="bert-input" className="mb-2 block font-medium">Text to analyse</label>
          <textarea id="bert-input" value={textInput} onChange={(event) => { setTextInput(event.target.value); setError(null); setSubmittedJobId(null); checkpoint.current = null; setReview(null) }} rows={7} maxLength={65_536} aria-describedby="bert-input-help" className="w-full rounded-lg border border-gray-300 p-3 leading-6 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-200" />
          <span id="bert-input-help" className="mt-2 block text-sm text-gray-600">UTF-8 text, maximum 510 characters. This conservative bound guarantees the input fits the worker's 512-token window without truncation.</span>
        </div> : <div><label htmlFor="resnet-input" className="mb-2 block font-medium">ResNet input image</label>
          <input id="resnet-input" type="file" accept={selectedModel ? modelMimeTypes(selectedModel).join(',') : undefined} onChange={(event) => { setInput(event.target.files?.[0] ?? null); setError(null); setSubmittedJobId(null); checkpoint.current = null; setReview(null) }} className="min-h-11 w-full rounded-lg border border-gray-300 p-3 file:mr-3 file:rounded file:border-0 file:bg-primary-50 file:px-3 file:py-2 file:font-medium file:text-primary-800" />
          {selectedModel?.max_input_size_mb ? <span className="mt-2 block text-sm text-gray-600">JPEG or PNG, maximum {selectedModel.max_input_size_mb} MB.</span> : null}
        </div>}
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
        {error || chainError ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"><p className="font-semibold">{chainError ? 'Job submission unavailable' : error?.startsWith('Image rejected:') ? 'The image was rejected' : error?.startsWith('BERT input rejected:') ? 'The text was rejected' : 'The job was not submitted'}</p><p className="mt-1 text-sm">{chainError ?? error}</p></div> : null}
        <button type="submit" disabled={stage !== null || submittedJobId !== null || models.length === 0 || chainError !== null} className="min-h-11 rounded-lg bg-primary-600 px-5 py-3 font-semibold text-white transition-colors hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50">
          {stage ? stageLabels[stage] : error && checkpoint.current ? 'Retry submission' : review ? 'Confirm upload and sign' : 'Review funding'}
        </button>
      </form>
      <aside aria-label="Submission overview" className="nebula-submission-aside">
        <p className="nebula-page-kicker">SUBMISSION OVERVIEW</p>
        <h2>Before you sign</h2>
        <dl>
          <div><dt>Approved model</dt><dd>{selectedModel?.name ?? 'Choose a model'}</dd></div>
          <div><dt>Listed model price</dt><dd>{selectedModel ? listedPrice(selectedModel.price_base_units) : 'Unavailable'}</dd></div>
          <div><dt>Input</dt><dd>{selectedModel?.input_type === 'text' ? `${Array.from(textInput).length} characters` : input?.name ?? 'No file selected'}</dd></div>
          <div><dt>Network</dt><dd>Arbitrum Sepolia</dd></div>
        </dl>
        <p className="nebula-submission-note">The exact escrow amount and wallet balance are checked against the live contract before signing. No job is funded until you confirm in your wallet.</p>
        {stage ? <p role="status" className="nebula-submission-stage">{stageLabels[stage]}</p> : null}
      </aside>
      </div>
      {submittedJobId ? <div role="status" className="mt-5 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-900"><p className="font-semibold">Escrow confirmed. Your job is ready for assignment.</p><Link to={`/user/jobs/${submittedJobId}`} className="mt-2 inline-flex min-h-11 items-center font-semibold underline underline-offset-4">Follow job progress</Link></div> : null}
    </div>
  )
}
