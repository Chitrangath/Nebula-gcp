import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listJobs } from '../../jobs/backend'
import { isTerminalJob, type Job } from '../../jobs/lifecycle'

function modelLabel(model: string): string {
  if (model === 'bert-base') return 'BERT sentiment'
  if (model === 'resnet50') return 'ResNet50 image classification'
  return model
}

export default function UserDashboard() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void listJobs(controller.signal)
      .then(setJobs)
      .catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Unable to load jobs') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision])

  const activeCount = jobs.filter((job) => !isTerminalJob(job.status) && !['expired_pre_escrow', 'attempts_exhausted'].includes(job.status)).length
  const settledCount = jobs.filter((job) => job.status === 'completed').length

  return <div className="nebula-workspace">
    <div className="nebula-page-heading">
      <div><p className="nebula-page-kicker">AI USER / JOBS</p><h1>My jobs</h1><p>Follow every job from escrow confirmation to verifier verdict and settlement.</p></div>
      <Link to="/user/submit" className="nebula-action-link">Submit a job <span aria-hidden="true">↗</span></Link>
    </div>
    <section aria-label="Job summary" className="nebula-metric-grid">
      <div className="nebula-metric"><span>Total jobs</span><strong>{jobs.length}</strong><small>Submitted by this wallet</small></div>
      <div className="nebula-metric"><span>Active jobs</span><strong>{activeCount}</strong><small>Awaiting terminal outcome</small></div>
      <div className="nebula-metric"><span>Settled jobs</span><strong>{settledCount}</strong><small>Completed on chain</small></div>
    </section>
    <section className="nebula-data-panel" aria-labelledby="jobs-heading">
      <div className="nebula-data-panel-head"><div><p className="nebula-page-kicker">ACTIVITY</p><h2 id="jobs-heading">Job history</h2></div><button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)} className="nebula-text-button">{loading ? 'Refreshing…' : 'Refresh'}</button></div>
      {loading && jobs.length === 0 ? <p role="status" className="nebula-panel-message">Loading jobs…</p> : null}
      {error ? <div role="alert" className="nebula-panel-message text-red-700">{error}{jobs.length > 0 ? <p className="mt-1">Showing last loaded job data.</p> : null} <button type="button" onClick={() => setRevision((value) => value + 1)} className="nebula-text-button">Retry</button></div> : null}
      {!loading && !error && jobs.length === 0 ? <div className="nebula-panel-message"><p>No jobs yet. Your first inference job will appear here.</p><Link to="/user/submit" className="nebula-inline-link">Create a job ↗</Link></div> : null}
      {jobs.length > 0 ? <ul className="nebula-job-list">{jobs.map((job) => <li key={job.id} className="nebula-job-row">
        <span className="nebula-job-icon" aria-hidden="true">{job.model_id === 'bert-base' ? 'B' : 'R'}</span>
        <div className="nebula-job-main"><Link to={`/user/jobs/${job.id}`}>{modelLabel(job.model_id)}</Link><span>Job {job.id} · {job.attempt_count} attempt(s)</span></div>
        <span className={`nebula-status nebula-status-${job.status}`}><span aria-hidden="true" />{job.status.replace(/_/g, ' ')}</span>
        <span className="nebula-job-date">{new Date(job.created_at).toLocaleDateString()}</span>
        <Link to={`/user/jobs/${job.id}`} className="nebula-job-open" aria-label={`Open ${modelLabel(job.model_id)} job`}><span aria-hidden="true">↗</span></Link>
        {job.reconciliation_health === 'critical_incident' ? <p className="nebula-job-warning">Reconciliation incident · chain state requires review</p> : null}
      </li>)}</ul> : null}
    </section>
  </div>
}
