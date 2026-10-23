import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listJobs } from '../../jobs/backend'
import type { Job } from '../../jobs/lifecycle'

export default function UserDashboard() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    void listJobs(controller.signal).then(setJobs).catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Unable to load jobs') }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])
  return <div className="max-w-4xl"><h1 className="text-2xl font-bold mb-6">User Dashboard</h1><div className="flex justify-between mb-6"><p className="text-gray-600">Submit and track your AI jobs.</p><Link to="/user/submit" className="text-primary-600">Submit a job</Link></div>{loading ? <p role="status">Loading jobs…</p> : null}{error ? <div role="alert" className="text-red-700">{error}<button type="button" onClick={() => window.location.reload()} className="ml-2 underline">Retry</button></div> : null}{!loading && !error && jobs.length === 0 ? <p className="text-gray-600">No jobs yet. Submit your first inference job.</p> : null}<ul className="space-y-3">{jobs.map((job) => <li key={job.id} className="rounded border p-4"><Link to={`/user/jobs/${job.id}`} className="font-medium text-primary-600">{job.model_id}</Link><span className="ml-4 rounded bg-gray-100 px-2 py-1 text-sm">{job.status}</span><span className="ml-4 text-sm text-gray-600">{job.reconciliation_health === 'critical_incident' ? 'reconciliation incident' : `${job.attempt_count} attempt(s)`}</span></li>)}</ul></div>
}
