import { useEffect, useState } from 'react'

import { getNetworkSnapshot, type NetworkNode, type NetworkSnapshot } from '../api/network'
import { ARBITRUM_SEPOLIA_EXPLORER } from '../utils/constants'

const statusClass: Record<string, string> = {
  online: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  pending: 'border-amber-200 bg-amber-50 text-amber-900',
  offline: 'border-gray-300 bg-gray-100 text-gray-800',
  disabled: 'border-red-200 bg-red-50 text-red-900',
}

function modelName(modelId: string): string {
  if (modelId === 'bert-base') return 'BERT sentiment'
  if (modelId === 'resnet50') return 'ResNet50 image classification'
  return modelId
}

function roleName(role: string): string {
  if (role === 'ai_user') return 'AI user'
  if (role === 'gpu_provider') return 'GPU provider'
  if (role === 'verifier') return 'Verifier'
  return role
}

function heartbeatLabel(age: number | null): string {
  if (age === null) return 'No heartbeat observed'
  if (age < 60) return `${age}s ago`
  const minutes = Math.floor(age / 60)
  return minutes === 1 ? '1 minute ago' : `${minutes} minutes ago`
}

function NodeCard({ node }: { node: NetworkNode }) {
  return <article aria-label={`${node.gpu_name ?? 'Unnamed GPU'} network node`} className="min-w-0 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary-700">GPU node</p>
        <h2 className="mt-1 text-xl font-bold text-gray-950">{node.gpu_name ?? 'Unnamed GPU'}</h2>
        <p className="mt-1 font-mono text-xs text-gray-600 [overflow-wrap:anywhere]">{node.id}</p>
      </div>
      <span className={`rounded-full border px-3 py-1 text-xs font-semibold capitalize ${statusClass[node.status] ?? statusClass.offline}`}>{node.status}</span>
    </div>

    <ul aria-label="Node roles" className="mt-4 flex flex-wrap gap-2">
      {node.roles.map((role) => <li key={role} className="rounded-full border border-primary-200 bg-primary-50 px-3 py-1 text-xs font-semibold text-primary-900">{roleName(role)}</li>)}
    </ul>

    <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
      <div><dt className="text-gray-600">VRAM</dt><dd className="mt-1 font-semibold text-gray-950">{node.vram_gb === null ? 'Not reported' : `${node.vram_gb} GB`}</dd></div>
      <div><dt className="text-gray-600">Last heartbeat</dt><dd className="mt-1 font-semibold text-gray-950">{heartbeatLabel(node.heartbeat_age_seconds)}</dd></div>
      <div className="min-w-0 sm:col-span-2"><dt className="text-gray-600">Provider wallet</dt><dd className="mt-1 font-mono text-sm [overflow-wrap:anywhere]"><a href={`${ARBITRUM_SEPOLIA_EXPLORER}/address/${node.provider_wallet_address}`} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center text-primary-700 underline underline-offset-4 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2">{node.provider_wallet_address}</a></dd></div>
    </dl>

    <section className="mt-5 border-t border-gray-100 pt-4">
      <h3 className="text-sm font-semibold text-gray-950">Model capabilities</h3>
      {node.supported_models.length > 0 ? <ul className="mt-2 flex flex-wrap gap-2">{node.supported_models.map((model) => <li key={model} className="rounded-full bg-gray-100 px-3 py-1 text-xs font-semibold text-gray-800">{modelName(model)}</li>)}</ul> : <p className="mt-2 text-sm text-gray-600">No executable model reported.</p>}
    </section>

    <div className="mt-5 grid gap-3 sm:grid-cols-2">
      <section className="min-w-0 rounded-lg border border-gray-200 bg-gray-50 p-4">
        <h3 className="text-sm font-semibold text-gray-950">Current lease</h3>
        {node.active_lease ? <><p className="mt-2 font-medium text-gray-950">{modelName(node.active_lease.model_id)} · {node.active_lease.status}</p><p className="mt-1 font-mono text-xs text-gray-600 [overflow-wrap:anywhere]">{node.active_lease.chain_job_id}</p><p className="mt-2 text-xs text-gray-600">Expires {new Date(node.active_lease.expires_at).toLocaleString()}</p></> : <p className="mt-2 text-sm text-gray-600">No active lease observed.</p>}
      </section>
      <section className="min-w-0 rounded-lg border border-gray-200 bg-gray-50 p-4">
        <h3 className="text-sm font-semibold text-gray-950">Last completed job</h3>
        {node.last_completed_job ? <><p className="mt-2 font-medium text-gray-950">{modelName(node.last_completed_job.model_id)}</p><p className="mt-1 font-mono text-xs text-gray-600 [overflow-wrap:anywhere]">{node.last_completed_job.chain_job_id}</p><p className="mt-2 text-xs text-gray-600">Completed {node.last_completed_job.completed_at ? new Date(node.last_completed_job.completed_at).toLocaleString() : 'time unavailable'}</p></> : <p className="mt-2 text-sm text-gray-600">No completed job observed.</p>}
      </section>
    </div>
  </article>
}

export default function Network() {
  const [snapshot, setSnapshot] = useState<NetworkSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    setLoading(true)
    setError(null)
    void getNetworkSnapshot(controller.signal)
      .then((value) => {
        setSnapshot(value)
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Could not load the network.')
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
          timer = setTimeout(() => setRevision((current) => current + 1), 10_000)
        }
      })
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [revision])

  const onlineCount = snapshot?.nodes.filter((node) => node.status === 'online').length ?? 0
  const activeLeaseCount = snapshot?.nodes.filter((node) => node.active_lease !== null).length ?? 0

  return <div className="nebula-workspace nebula-network-page">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-primary-700">Infrastructure / observed state</p>
        <h1 className="text-3xl font-bold tracking-tight text-gray-950">Live compute network</h1>
        <p className="mt-2 max-w-3xl leading-6 text-gray-600">Inspect registered GPU nodes, model compatibility, heartbeat health, and lease activity from one authenticated view.</p>
      </div>
      <button type="button" disabled={loading} onClick={() => setRevision((current) => current + 1)} className="inline-flex min-h-11 items-center rounded-lg border border-primary-600 bg-white px-5 py-3 font-semibold text-primary-700 hover:bg-primary-50 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2 disabled:cursor-wait disabled:opacity-50">{loading ? 'Refreshing…' : 'Refresh network'}</button>
    </div>

    {error ? <div role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-900"><p>{error}</p>{snapshot ? <p className="mt-1 text-sm">Showing last observed network data. Current node status may have changed.</p> : null}<button type="button" onClick={() => setRevision((current) => current + 1)} className="mt-2 min-h-11 font-semibold underline underline-offset-4 focus:outline-none focus:ring-2 focus:ring-red-700 focus:ring-offset-2">Retry network</button></div> : null}
    {loading && !snapshot ? <p role="status" className="mt-8 text-gray-700">Loading live network state…</p> : null}

    {snapshot ? <>
      <p className="mt-6 text-sm text-gray-600">Network observed at {new Date(snapshot.observed_at).toLocaleTimeString()} · {snapshot.nodes.length} registered GPU nodes</p>
      <p role="status" aria-atomic="true" className="sr-only">{onlineCount} of {snapshot.nodes.length} GPU nodes online; {activeLeaseCount} active leases.</p>
      <section aria-label="Network summary" className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[['GPU nodes registered', snapshot.nodes.length], ['Online GPU nodes', onlineCount], ['Active leases', activeLeaseCount], ['Chain ID', snapshot.chain_id]].map(([label, value]) => <div key={label} className="rounded-xl border border-gray-200 bg-white p-4"><p className="text-sm text-gray-600">{label}</p><p className="mt-1 font-mono text-2xl font-bold text-gray-950">{value}</p></div>)}
      </section>

      <section aria-label="Connected browser" className="mt-6 rounded-xl border border-primary-200 bg-primary-50 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-primary-700">Connected browser</p><h2 className="mt-1 text-xl font-bold text-gray-950">This browser · {roleName(snapshot.viewer.role)}</h2></div><span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-900">Authenticated</span></div>
        <p className="mt-3 font-mono text-sm [overflow-wrap:anywhere]">{snapshot.viewer.wallet_address}</p>
      </section>

      <section aria-label="Evidence boundaries" className="mt-6 grid gap-4 rounded-xl border border-gray-200 bg-white p-5 md:grid-cols-2">
        <div><h2 className="font-bold text-gray-950">Backend-observed</h2><p className="mt-2 text-sm leading-6 text-gray-600">Node heartbeat age, effective availability, model capability, current lease, and completed-job history come from Nebula’s authenticated runtime database.</p></div>
        <div><h2 className="font-bold text-gray-950">On-chain authority</h2><p className="mt-2 text-sm leading-6 text-gray-600">Escrow settlement is authoritative on Arbitrum Sepolia, chain ID {snapshot.chain_id}. The configured Verifier authorizes the terminal verdict.</p>{snapshot.verifier_address ? <a href={`${ARBITRUM_SEPOLIA_EXPLORER}/address/${snapshot.verifier_address}`} target="_blank" rel="noreferrer" className="mt-2 inline-flex min-h-11 items-center font-mono text-sm text-primary-700 underline underline-offset-4 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2">Verifier {snapshot.verifier_address}</a> : <p className="mt-2 text-sm font-semibold text-amber-800">Verifier address is not configured.</p>}</div>
      </section>

      <section aria-labelledby="gpu-network-heading" className="mt-8">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 id="gpu-network-heading" className="text-2xl font-bold text-gray-950">Registered GPU nodes</h2><p className="mt-1 text-gray-600">Status changes are refreshed every 10 seconds.</p></div><p className="text-sm text-gray-600">Heartbeat expiry: {snapshot.heartbeat_ttl_seconds}s</p></div>
        {snapshot.nodes.length > 0 ? <div className="mt-4 grid gap-4 lg:grid-cols-2">{snapshot.nodes.map((node) => <NodeCard key={node.id} node={node} />)}</div> : <div className="mt-4 rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center"><h3 className="font-semibold text-gray-950">No GPU nodes registered</h3><p className="mt-2 text-gray-600">Register and start a provider Worker to make it visible here.</p></div>}
      </section>
    </> : null}
  </div>
}
