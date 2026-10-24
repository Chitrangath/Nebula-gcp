import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { downloadJobResult, getJobResult, probabilityFromHexFloat, type JobResult } from '../../jobs/backend'
import { useJobLifecycle, type Job } from '../../jobs/lifecycle'
import { ARBITRUM_SEPOLIA_EXPLORER } from '../../utils/constants'

interface TransactionEvidence {
  hash: string
  status: string
  chain_id: number
  block_number: number | null
}

function transactionEvidence(value: unknown): TransactionEvidence | null {
  if (!value || typeof value !== 'object') return null
  const evidence = value as Record<string, unknown>
  if (typeof evidence.hash !== 'string' || !/^0x[0-9a-fA-F]{64}$/.test(evidence.hash) ||
      typeof evidence.status !== 'string' || typeof evidence.chain_id !== 'number' ||
      !Number.isSafeInteger(evidence.chain_id) || evidence.chain_id <= 0 ||
      (evidence.block_number !== null && (typeof evidence.block_number !== 'number' ||
        !Number.isSafeInteger(evidence.block_number) || evidence.block_number < 0))) return null
  return evidence as unknown as TransactionEvidence
}

function ChainEvidence({ job }: { job: Job }) {
  const transactions = [
    ['Escrow transaction', job.escrow_transaction],
    ['Assignment transaction', job.assignment_transaction],
    ['Proof transaction', job.proof_transaction],
    ['Settlement transaction', job.settlement_transaction],
    ['Refund transaction', job.refund_transaction],
  ].flatMap(([label, value]) => {
    const evidence = transactionEvidence(value)
    return evidence?.chain_id === job.chain_id ? [{ label: String(label), evidence }] : []
  })
  return <section aria-labelledby="chain-evidence-heading" className="mt-6 rounded-xl border border-gray-200 bg-white p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="chain-evidence-heading" className="text-lg font-semibold text-gray-900">Arbitrum Sepolia evidence</h2><p className="mt-1 max-w-3xl text-sm leading-6 text-gray-600">These values are observed by the backend from the configured chain. Open any transaction independently in Arbiscan.</p></div>
      <span className="rounded-full border border-primary-200 bg-primary-50 px-3 py-1 font-mono text-sm font-semibold text-primary-900">Chain ID {job.chain_id}</span>
    </div>
    {transactions.length > 0 ? <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{transactions.map(({ label, evidence }) => <article key={label} className="min-w-0 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <h3 className="font-semibold text-gray-900">{label}</h3>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm"><div><dt className="text-gray-600">Status</dt><dd className="font-medium">{evidence.status}</dd></div><div><dt className="text-gray-600">Block number</dt><dd className="font-mono font-medium">{evidence.block_number ?? 'Pending'}</dd></div></dl>
      <a href={`${ARBITRUM_SEPOLIA_EXPLORER}/tx/${evidence.hash}`} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-11 items-center font-semibold text-primary-700 underline underline-offset-4 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2">Open {label.toLowerCase()} in Arbiscan</a>
    </article>)}</div> : <p className="mt-4 text-sm text-gray-600">No chain transaction has been observed for this job yet.</p>}
  </section>
}

function Lifecycle({ job }: { job: Job }) {
  const ranks: Record<string, number> = { pending_blockchain: 0, queued: 1, retry_pending: 1, assigned: 2, running: 3, proof_submitted: 4, verifying: 4, settling: 5, completed: 6 }
  const escrowConfirmed = job.status !== 'expired_pre_escrow' && Boolean(job.escrow_transaction)
  const rank = ranks[job.status] ?? (escrowConfirmed ? 1 : 0)
  const stages = [
    { label: rank === 0 ? 'Escrow pending' : 'Escrow confirmed', complete: rank >= 1 },
    { label: 'Queued', complete: rank >= 1 },
    { label: 'Assigned', complete: rank >= 2 },
    { label: 'Running', complete: rank >= 3 },
    { label: 'Proof verified', complete: job.proof_verification_status === 'valid' },
    { label: 'Settled', complete: job.on_chain_state === 'Settled' && job.status === 'completed' },
  ]
  return <ol aria-label="Job lifecycle" className="grid gap-2 text-sm sm:grid-cols-3 lg:grid-cols-6">
    {stages.map((stage, index) => <li key={stage.label} className={`rounded-lg border p-3 ${stage.complete ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-gray-200 bg-gray-50 text-gray-600'}`}>
      <span className="block font-mono text-xs">{stage.complete ? 'Done' : `Step ${index + 1}`}</span>
      <span className="mt-1 block font-medium">{stage.label}</span>
    </li>)}
  </ol>
}

function percentage(value: string): string {
  const probability = probabilityFromHexFloat(value)
  return probability === null ? value : `${(probability * 100).toFixed(1)}% confidence`
}

function ResultPreview({ result }: { result: JobResult }) {
  if (result.model_id === 'bert-base') {
    const selected = result.scores.find((score) => score.stars === result.stars)
    return <section aria-label="Inference result" className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-5">
      <p className="text-sm font-semibold uppercase tracking-wide text-emerald-800">Verified inference result</p>
      <h2 className="mt-2 text-2xl font-bold text-emerald-950">{result.stars}-star sentiment</h2>
      <p className="mt-1 text-emerald-900">{selected ? percentage(selected.probability_hex) : 'Verified score unavailable'}</p>
      <ol className="mt-4 grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
        {result.scores.map((score) => <li key={score.stars} className="rounded border border-emerald-200 bg-white p-2"><span className="font-semibold">{score.stars} star</span><span className="block text-xs text-gray-600">{percentage(score.probability_hex)}</span></li>)}
      </ol>
    </section>
  }
  return <section aria-label="Inference result" className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-5">
    <p className="text-sm font-semibold uppercase tracking-wide text-emerald-800">Verified inference result</p>
    <h2 className="mt-2 text-xl font-bold text-emerald-950">Top image classes</h2>
    <ol className="mt-4 grid gap-2 sm:grid-cols-2">
      {result.top_k.map((match) => <li key={match.index} className="rounded border border-emerald-200 bg-white p-3"><span className="font-semibold">ImageNet class {match.index}</span><span className="ml-2 text-sm text-gray-600">{percentage(match.probability_hex)}</span></li>)}
    </ol>
  </section>
}

export default function JobDetail() {
  const { id } = useParams()
  const { job, loading, error, retry } = useJobLifecycle(id)
  const [result, setResult] = useState<JobResult | null>(null)
  const [resultError, setResultError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const downloadController = useRef<AbortController | null>(null)
  const canAccessResult = Boolean(job && job.status === 'completed' && job.result_available && job.reconciliation_health !== 'critical_incident')

  useEffect(() => {
    setResult(null); setResultError(null)
    if (!id || !canAccessResult) return
    const controller = new AbortController()
    void getJobResult(id, controller.signal).then(setResult).catch((caught) => { if (!controller.signal.aborted) setResultError(caught instanceof Error ? caught.message : 'Unable to display result') })
    return () => controller.abort()
  }, [canAccessResult, id])

  useEffect(() => () => downloadController.current?.abort(), [])

  async function download(): Promise<void> {
    if (!id || !canAccessResult) return
    const controller = new AbortController(); downloadController.current = controller; setDownloading(true); setResultError(null)
    try {
      const blob = await downloadJobResult(id, controller.signal)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `nebula-${id}-result.json`; anchor.click(); URL.revokeObjectURL(url)
    } catch (caught) { if (!controller.signal.aborted) setResultError(caught instanceof Error ? caught.message : 'Unable to download result') }
    finally { if (!controller.signal.aborted) setDownloading(false) }
  }

  return <main className="mx-auto max-w-6xl">
    <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-primary-700">AI user workspace</p>
    <h1 className="text-3xl font-bold tracking-tight">Job progress</h1>
    {loading ? <p role="status" className="mt-6">Loading job…</p> : null}
    {error ? <div role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error.message}<button type="button" onClick={retry} className="ml-2 min-h-11 font-semibold underline">Retry</button></div> : null}
    {job ? <>
      <div className="my-6 flex flex-wrap items-center gap-3"><span className="rounded-full bg-primary-50 px-3 py-1 text-sm font-semibold text-primary-800">{job.status.replace(/_/g, ' ')}</span><span className="font-medium">{job.model_id}</span></div>
      <Lifecycle job={job} />
      {['failed', 'attempts_exhausted', 'expired_pre_escrow'].includes(job.status) ? <p role="alert" className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">This job failed. No successful result is available; review the status and submit a new job if needed.</p> : null}
      {['refunded', 'awaiting_timeout_refund'].includes(job.status) ? <p role="status" className="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900">This job did not settle to a provider. Refund state: {job.refund_status ?? job.status.replace(/_/g, ' ')}.</p> : null}
      {job.reconciliation_health === 'critical_incident' ? <p role="alert" className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">A reconciliation incident is open. Chain/database state is not currently authoritative for this job.</p> : null}
      {job.assigned_node_id ? <section aria-label="Assigned provider" className="mt-6 rounded-xl border border-gray-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-gray-900">Assigned provider</h2>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          <div><dt className="text-gray-600">GPU</dt><dd className="font-medium">{job.assigned_gpu_name ?? 'GPU node'}</dd></div>
          <div><dt className="text-gray-600">Lease</dt><dd className="font-medium">{job.current_lease_status ?? 'Pending confirmation'}</dd></div>
          <div className="min-w-0"><dt className="text-gray-600">Node ID</dt><dd className="font-mono [overflow-wrap:anywhere]">{job.assigned_node_id}</dd></div>
          <div className="min-w-0"><dt className="text-gray-600">Provider wallet</dt><dd className="font-mono [overflow-wrap:anywhere]">{job.assigned_provider_address ?? 'Awaiting provider identity'}</dd></div>
        </dl>
      </section> : null}
      {result ? <ResultPreview result={result} /> : null}
      {canAccessResult && !result && !resultError ? <p role="status" className="mt-6">Loading verified result…</p> : null}
      {resultError ? <p role="alert" className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{resultError}. Retry by refreshing this job.</p> : null}
      <dl className="mt-6 grid gap-4 rounded-xl border border-gray-200 bg-white p-5 sm:grid-cols-2">
        <div><dt className="text-sm text-gray-600">On-chain state</dt><dd className="font-medium">{job.on_chain_state ?? 'Pending'}</dd></div>
        <div><dt className="text-sm text-gray-600">Proof verification</dt><dd className="font-medium">{job.proof_verification_status ?? 'Pending'}</dd></div>
        <div><dt className="text-sm text-gray-600">Provider credit</dt><dd className="font-medium">{job.provider_payment_credit_status ?? 'Not credited'}</dd></div>
        <div><dt className="text-sm text-gray-600">User refund</dt><dd className="font-medium">{job.refund_status ?? 'Not credited'}</dd></div>
        <div><dt className="text-sm text-gray-600">Attempts</dt><dd className="font-medium">{job.attempt_count}</dd></div>
        <div className="min-w-0"><dt className="text-sm text-gray-600">Expected fingerprint</dt><dd className="font-mono text-sm [overflow-wrap:anywhere]">{job.fingerprint ?? 'Pending'}</dd></div>
        <div className="min-w-0"><dt className="text-sm text-gray-600">Submitted proof fingerprint</dt><dd className="font-mono text-sm [overflow-wrap:anywhere]">{job.proof_fingerprint ?? 'Pending'}</dd></div>
      </dl>
      <ChainEvidence job={job} />
      {canAccessResult ? <button type="button" onClick={() => void download()} disabled={downloading} className="mt-5 min-h-11 rounded-lg bg-primary-600 px-5 py-3 font-semibold text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2 disabled:cursor-wait disabled:opacity-50">{downloading ? 'Preparing result…' : 'Download result'}</button> : null}
      <p className="mt-6"><Link to="/user/dashboard" className="inline-flex min-h-11 items-center font-semibold text-primary-700 underline underline-offset-4">Back to jobs</Link></p>
    </> : null}
  </main>
}
