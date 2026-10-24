import { useState, type FormEvent } from 'react'
import { ApiProblemError } from '../../api/client'
import { registerProviderNode, type RegisterNodeResponse } from '../../api/nodes'

function safeError(error: unknown): string {
  if (error instanceof ApiProblemError) return error.message
  return 'Node registration failed. Check your provider wallet and try again.'
}

export default function RegisterNode() {
  const [gpuName, setGpuName] = useState('')
  const [vram, setVram] = useState('')
  const [location, setLocation] = useState('')
  const [signer, setSigner] = useState('')
  const [result, setResult] = useState<RegisterNodeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault(); setError(null); setResult(null); setSubmitting(true)
    try {
      setResult(await registerProviderNode({ gpu_name: gpuName.trim() || undefined, vram_gb: vram ? Number(vram) : undefined, location: location.trim() || undefined, worker_signer_address: signer.trim() || undefined }))
    } catch (caught) { setError(safeError(caught)) } finally { setSubmitting(false) }
  }

  return <main className="mx-auto max-w-2xl">
    <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-primary-700">Provider onboarding</p>
    <h1 className="text-3xl font-bold tracking-tight">Register a GPU node</h1>
    <p className="mt-2 text-gray-600">Register this device once, then keep the API key private. Your worker uses it for authenticated heartbeats and leases.</p>
    <form onSubmit={(event) => void submit(event)} className="mt-8 space-y-5 rounded-xl border bg-white p-6 shadow-sm">
      <label className="block"><span className="mb-1 block font-medium">GPU name</span><input required value={gpuName} onChange={(event) => setGpuName(event.target.value)} placeholder="NVIDIA RTX 3050" className="min-h-11 w-full rounded-lg border p-3" /></label>
      <label className="block"><span className="mb-1 block font-medium">VRAM (GB)</span><input required min="1" type="number" value={vram} onChange={(event) => setVram(event.target.value)} className="min-h-11 w-full rounded-lg border p-3" /></label>
      <label className="block"><span className="mb-1 block font-medium">Location</span><input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="IN / Mumbai" className="min-h-11 w-full rounded-lg border p-3" /></label>
      <label className="block"><span className="mb-1 block font-medium">Worker signer address <span className="font-normal text-gray-500">(optional)</span></span><input value={signer} onChange={(event) => setSigner(event.target.value)} placeholder="0x…" className="min-h-11 w-full rounded-lg border p-3" /></label>
      <button disabled={submitting} className="min-h-11 rounded-lg bg-primary-600 px-5 font-semibold text-white disabled:cursor-wait disabled:opacity-60">{submitting ? 'Registering…' : 'Register node'}</button>
      {error ? <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-800">{error}</p> : null}
      {result ? <section aria-live="polite" className="rounded-lg border border-emerald-200 bg-emerald-50 p-4"><h2 className="font-semibold text-emerald-900">Node registered</h2><p className="mt-2 text-sm text-emerald-900">Save this API key now. It is shown only once.</p><dl className="mt-3 space-y-2 break-all text-sm"><div><dt className="font-medium">Node ID</dt><dd>{result.node_id}</dd></div><div><dt className="font-medium">Worker API key</dt><dd className="font-mono">{result.api_key}</dd></div></dl></section> : null}
    </form>
  </main>
}
