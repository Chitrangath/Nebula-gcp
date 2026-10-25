import { Link } from 'react-router-dom'

const features = [
  { index: '01 / COMPUTE', title: 'Explore the GPU network', description: 'See registered GPU nodes, supported models, live heartbeats, and current leases.', to: '/network', link: 'View network' },
  { index: '02 / INFERENCE', title: 'Run a model', description: 'Choose ResNet50 or BERT, submit an exact input, and follow the job from escrow to result.', to: '/user/submit', link: 'Create a job' },
  { index: '03 / SETTLEMENT', title: 'Verify and get paid', description: 'Inspect the verifier verdict and on-chain settlement. Providers withdraw credited earnings.', to: '/provider/dashboard', link: 'Provider console' },
] as const

export default function Home() {
  return <div>
    <section className="nebula-hero" aria-labelledby="home-title">
      <div className="nebula-orbit" aria-hidden="true"><span className="nebula-orbit-point one" /><span className="nebula-orbit-point two" /><span className="nebula-orbit-point three" /></div>
      <div className="nebula-hero-copy">
        <span className="nebula-eyebrow"><span aria-hidden="true" /> GPU COMPUTE · VERIFIED EXECUTION</span>
        <h1 id="home-title">Nebula AI Cloud<em>Compute with proof.</em></h1>
        <p>Run approved AI models on independently operated GPU nodes. Track each job through its lease, PoAE proof, verifier verdict, and Arbitrum Sepolia settlement.</p>
        <div className="nebula-hero-actions">
          <Link to="/user/submit" className="nebula-button-primary">Submit a Job <span aria-hidden="true">↗</span></Link>
          <Link to="/provider/register" className="nebula-button-secondary">Become a Provider <span aria-hidden="true">↗</span></Link>
        </div>
      </div>
    </section>
    <div className="nebula-section-heading"><div><h2>One network. Two ways to participate.</h2><p>Everything needed to follow a job is visible in the workspace.</p></div><span className="text-xs font-semibold uppercase tracking-widest text-gray-500">ARBITRUM SEPOLIA · TESTNET</span></div>
    <div className="nebula-feature-grid">{features.map((feature) => <article className="nebula-feature-card" key={feature.index}>
      <small>{feature.index}</small><h3>{feature.title}</h3><p>{feature.description}</p><Link to={feature.to}>{feature.link} <span aria-hidden="true">↗</span></Link>
    </article>)}</div>
  </div>
}
