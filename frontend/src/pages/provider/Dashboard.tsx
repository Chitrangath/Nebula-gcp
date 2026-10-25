import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getProviderDashboard, type ProviderDashboardData, type ProviderNode } from '../../api/nodes'
import { getAuthenticatedWallet } from '../../api/session'
import { ARBITRUM_SEPOLIA_EXPLORER } from '../../utils/constants'
import { withdrawInjectedWallet } from '../../jobs/chain'

const statusClass: Record<string, string> = { online: 'border-emerald-200 bg-emerald-50 text-emerald-900', pending: 'border-amber-200 bg-amber-50 text-amber-900', offline: 'border-gray-200 bg-gray-100 text-gray-700', disabled: 'border-red-200 bg-red-50 text-red-800' }

function modelName(modelId: string): string {
  return modelId === 'bert-base' ? 'BERT sentiment' : modelId === 'resnet50' ? 'ResNet50 image classification' : modelId
}

function baseUnits(value: string | null): string {
  if (value === null) return 'Unavailable'
  try { return `${BigInt(value).toLocaleString()} base units` } catch { return `${value} base units` }
}

function NodeCard({ node }: { node: ProviderNode }) {
  return <article className="rounded-xl border border-gray-200 bg-white p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0"><h2 className="text-lg font-semibold">{node.gpu_name ?? 'Unnamed GPU'}</h2><p className="mt-1 font-mono text-xs text-gray-500 [overflow-wrap:anywhere]">{node.id}</p></div>
      <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusClass[node.status] ?? statusClass.offline}`}>{node.status}</span>
    </div>
    <dl className="mt-5 grid grid-cols-2 gap-4 text-sm">
      <div><dt className="text-gray-500">VRAM</dt><dd className="font-medium">{node.vram_gb ? `${node.vram_gb} GB` : '—'}</dd></div>
      <div><dt className="text-gray-500">Active leases</dt><dd className="font-medium">{node.active_leases}</dd></div>
      <div className="col-span-2"><dt className="text-gray-500">Last heartbeat</dt><dd className="font-medium">{node.last_heartbeat ? new Date(node.last_heartbeat).toLocaleString() : 'No heartbeat yet'}</dd></div>
      <div className="col-span-2 min-w-0"><dt className="text-gray-500">Worker signer</dt><dd className="font-mono [overflow-wrap:anywhere]">{node.worker_signer_address ?? 'Not configured'}</dd></div>
    </dl>
    <section className="mt-5 border-t border-gray-100 pt-4"><h3 className="text-sm font-semibold text-gray-900">Model capabilities</h3><ul className="mt-2 flex flex-wrap gap-2">{node.supported_models.map((model) => <li key={model} className="rounded-full bg-primary-50 px-3 py-1 text-xs font-semibold text-primary-800">{modelName(model)}</li>)}</ul></section>
    <section aria-label={`Active work for ${node.gpu_name ?? node.id}`} className="mt-5 rounded-lg border border-gray-200 bg-gray-50 p-4">
      <h3 className="text-sm font-semibold text-gray-900">Current work</h3>
      {node.active_lease ? <><p className="mt-2 font-medium">Active · {modelName(node.active_lease.model_id)}</p><p className="mt-1 font-mono text-xs text-gray-600 [overflow-wrap:anywhere]">Job {node.active_lease.job_id}</p><p className="mt-1 text-xs text-gray-600">Lease expires {new Date(node.active_lease.expires_at).toLocaleString()}</p></> : <p className="mt-2 text-sm text-gray-600">Available for a compatible job.</p>}
    </section>
    {node.recent_jobs.length > 0 ? <section className="mt-5"><h3 className="text-sm font-semibold text-gray-900">Recent completed work</h3><ul className="mt-2 space-y-2">{node.recent_jobs.map((job) => <li key={job.job_id} className="rounded border border-gray-100 p-3 text-sm"><span className="font-medium">{modelName(job.model_id)}</span><span className="ml-2 text-gray-600">completed {job.completed_at ? new Date(job.completed_at).toLocaleString() : ''}</span><span className="mt-1 block font-mono text-xs text-gray-500 [overflow-wrap:anywhere]">{job.job_id}</span></li>)}</ul></section> : null}
  </article>
}

export default function ProviderDashboard() {
  const [dashboard, setDashboard] = useState<ProviderDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState<string | null>(null)
  const wallet = getAuthenticatedWallet()

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    setLoading(true); setError(null)
    void getProviderDashboard(controller.signal)
      .then((data) => { setDashboard(data); timer = setTimeout(() => setRevision((value) => value + 1), 15_000) })
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Could not load the provider dashboard.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [revision])

  async function withdraw(): Promise<void> {
    if (!window.ethereum) { setWithdrawError('Install and connect MetaMask first.'); return }
    setWithdrawing(true); setWithdrawError(null)
    try { await withdrawInjectedWallet(window.ethereum); setRevision((value) => value + 1) }
    catch (caught) { setWithdrawError(caught instanceof Error ? caught.message : 'Withdrawal failed.') }
    finally { setWithdrawing(false) }
  }

  return <main className="mx-auto max-w-6xl">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-sm font-semibold uppercase tracking-wide text-primary-700">Provider workspace</p><h1 className="text-3xl font-bold tracking-tight">GPU provider dashboard</h1><p className="mt-2 text-gray-600">Monitor node health, assigned work, completed jobs, and testnet earnings.</p></div><Link to="/provider/register" className="inline-flex min-h-11 items-center rounded-lg bg-primary-600 px-5 py-3 font-semibold text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2">Register a node</Link></div>
    <section aria-label="Provider identity" className="mt-6 rounded-xl border border-gray-200 bg-white p-5"><h2 className="text-sm font-semibold uppercase tracking-wide text-gray-600">Authenticated provider wallet</h2><p className="mt-2 font-mono text-sm [overflow-wrap:anywhere]">{wallet ?? 'Reconnect your provider wallet to restore identity.'}</p></section>
    {loading && !dashboard ? <p role="status" className="mt-8">Loading provider state…</p> : null}
    {error ? <div role="alert" className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"><p>{error}</p><button type="button" onClick={() => setRevision((value) => value + 1)} className="mt-2 min-h-11 font-semibold underline underline-offset-4">Retry dashboard</button></div> : null}
    {dashboard ? <>
      <section aria-labelledby="earnings-heading" className="mt-8"><h2 id="earnings-heading" className="text-xl font-bold">Earnings overview</h2><dl className="mt-4 grid gap-4 sm:grid-cols-3"><div className="rounded-xl border border-gray-200 bg-white p-5"><dt className="text-sm text-gray-600">Total credited</dt><dd className="mt-2 text-xl font-bold">{baseUnits(dashboard.earnings.total_credited_base_units)}</dd></div><div className="rounded-xl border border-gray-200 bg-white p-5"><dt className="text-sm text-gray-600">Pending withdrawal</dt><dd className="mt-2 text-xl font-bold">{baseUnits(dashboard.earnings.pending_withdrawal_base_units)}</dd><p className="mt-1 text-xs text-gray-500">{dashboard.earnings.pending_withdrawal_status}</p>{dashboard.earnings.pending_withdrawal_base_units && BigInt(dashboard.earnings.pending_withdrawal_base_units) > 0n ? <button type="button" onClick={() => void withdraw()} disabled={withdrawing} className="mt-4 min-h-11 rounded-lg bg-primary-600 px-4 py-2 font-semibold text-white hover:bg-primary-700 disabled:opacity-60">{withdrawing ? 'Withdrawing…' : 'Withdraw funds'}</button> : null}{withdrawError ? <p role="alert" className="mt-2 text-sm text-red-700">{withdrawError}</p> : null}</div><div className="rounded-xl border border-gray-200 bg-white p-5"><dt className="text-sm text-gray-600">Withdrawn</dt><dd className="mt-2 text-xl font-bold">{baseUnits(dashboard.earnings.total_withdrawn_base_units)}</dd></div></dl></section>
      <section aria-labelledby="nodes-heading" className="mt-8"><div className="flex items-center justify-between gap-4"><h2 id="nodes-heading" className="text-xl font-bold">Your GPU nodes</h2>{loading ? <span role="status" className="text-sm text-gray-600">Refreshing…</span> : null}</div>{dashboard.nodes.length === 0 ? <div className="mt-4 rounded-xl border border-dashed border-gray-300 p-8 text-center"><h3 className="font-semibold">No nodes registered</h3><p className="mt-2 text-gray-600">Register this device to join the provider network.</p></div> : <div className="mt-4 grid gap-4 lg:grid-cols-2">{dashboard.nodes.map((node) => <NodeCard key={node.id} node={node} />)}</div>}</section>
      <section aria-labelledby="credits-heading" className="mt-8"><h2 id="credits-heading" className="text-xl font-bold">Completed jobs &amp; credits</h2>{dashboard.earnings.credits.length === 0 ? <p className="mt-3 text-gray-600">No settled provider credits yet.</p> : <ul className="mt-4 space-y-3">{dashboard.earnings.credits.map((credit) => <li key={`${credit.job_id}-${credit.blockchain_tx_hash ?? credit.credited_at ?? 'credit'}`} className="rounded-xl border border-gray-200 bg-white p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="font-semibold">{baseUnits(credit.amount_base_units)}</p><p className="mt-1 font-mono text-xs text-gray-500 [overflow-wrap:anywhere]">Job {credit.job_id}</p></div><span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-900">{credit.status}</span></div>{credit.blockchain_tx_hash && /^0x[0-9a-fA-F]{64}$/.test(credit.blockchain_tx_hash) ? <a href={`${ARBITRUM_SEPOLIA_EXPLORER}/tx/${credit.blockchain_tx_hash}`} target="_blank" rel="noreferrer" className="mt-3 inline-flex min-h-11 items-center font-semibold text-primary-700 underline underline-offset-4">View settlement transaction</a> : null}</li>)}</ul>}</section>
    </> : null}
  </main>
}
