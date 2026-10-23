import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ARBITRUM_SEPOLIA_EXPLORER } from '../../utils/constants'
import { downloadJobResult } from '../../jobs/backend'
import { isTerminalJob, useJobLifecycle, type Job } from '../../jobs/lifecycle'

function explorerLink(value: unknown): string | null {
  if (!value || typeof value !== 'object' || !('hash' in value) || typeof value.hash !== 'string' || !/^0x[0-9a-fA-F]{64}$/.test(value.hash)) return null
  return `${ARBITRUM_SEPOLIA_EXPLORER}/tx/${value.hash}`
}

function Lifecycle({ job }: { job: Job }) {
  const states = ['pending_blockchain', 'queued', 'assigned', 'running', 'completed']
  const current = states.indexOf(job.status)
  return <ol aria-label="Job lifecycle" className="flex flex-wrap gap-2 text-sm">{states.map((state, index) => <li key={state} className={index <= current ? 'rounded bg-green-100 px-2 py-1 text-green-800' : 'rounded bg-gray-100 px-2 py-1 text-gray-500'}>{state}</li>)}</ol>
}

export default function JobDetail() {
  const { id } = useParams(); const { job, loading, error, retry } = useJobLifecycle(id); const [downloading, setDownloading] = useState(false); const [downloadError, setDownloadError] = useState<string | null>(null); const downloadController = useRef<AbortController | null>(null)
  useEffect(() => () => downloadController.current?.abort(), [])
  async function download(): Promise<void> { if (!id) return; const controller = new AbortController(); downloadController.current = controller; setDownloading(true); setDownloadError(null); try { const blob = await downloadJobResult(id, controller.signal); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `nebula-${id}-result`; anchor.click(); URL.revokeObjectURL(url) } catch (caught) { if (!controller.signal.aborted) setDownloadError(caught instanceof Error ? caught.message : 'Unable to download result') } finally { if (!controller.signal.aborted) setDownloading(false) } }
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold mb-6">Job Detail</h1>
      {loading ? <p role="status">Loading job…</p> : null}{error ? <div role="alert" className="text-red-700">{error.message}<button type="button" onClick={retry} className="ml-2 underline">Retry</button></div> : null}
      {job ? <><div className="mb-6 flex items-center gap-3"><span className="rounded bg-gray-100 px-2 py-1">{job.status}</span><span>{job.model_id}</span></div><Lifecycle job={job} />{job.reconciliation_health === 'critical_incident' ? <p role="alert" className="mt-4 text-red-700">A reconciliation incident is open. Chain/database state is not currently authoritative for this job.</p> : null}{downloadError ? <p role="alert" className="mt-4 text-red-700">{downloadError}</p> : null}<dl className="mt-6 grid gap-3 sm:grid-cols-2"><div><dt className="font-medium">On-chain state</dt><dd>{job.on_chain_state ?? 'pending'}</dd></div><div><dt className="font-medium">Proof verification</dt><dd>{job.proof_verification_status ?? 'pending'}</dd></div><div><dt className="font-medium">Attempts</dt><dd>{job.attempt_count}</dd></div><div><dt className="font-medium">Fingerprint</dt><dd className="break-all">{job.fingerprint ?? 'pending'}</dd></div></dl><div className="mt-6 flex flex-wrap gap-3">{([['Escrow transaction', job.escrow_transaction], ['Assignment transaction', job.assignment_transaction], ['Proof transaction', job.proof_transaction], ['Settlement transaction', job.settlement_transaction]] as Array<[string, unknown]>).map(([label, value]) => { const href = explorerLink(value); return href ? <a key={label} href={href} target="_blank" rel="noreferrer" className="text-primary-600 underline">{label}</a> : null })}</div>{job.result_available && job.reconciliation_health !== 'critical_incident' ? <button type="button" onClick={() => void download()} disabled={downloading || !isTerminalJob(job.status)} className="mt-6 rounded bg-primary-600 px-4 py-2 text-white disabled:opacity-60">{downloading ? 'Preparing result…' : 'Download result'}</button> : null}<p className="mt-6"><Link to="/user/dashboard" className="text-primary-600 underline">Back to jobs</Link></p></> : null}
    </div>
  )
}
