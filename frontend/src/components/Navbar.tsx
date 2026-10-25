import { useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

const sections = [
  { label: 'Overview', to: '/', marker: '01' },
  { label: 'GPU network', to: '/network', marker: '02' },
  { label: 'My jobs', to: '/user/dashboard', marker: '03' },
  { label: 'New job', to: '/user/submit', marker: '04' },
  { label: 'Provider console', to: '/provider/dashboard', marker: '05' },
  { label: 'Register node', to: '/provider/register', marker: '06' },
] as const

function Brand() {
  return <Link to="/" className="nebula-brand" aria-label="Nebula AI Cloud home">
    <span className="nebula-brand-mark" aria-hidden="true"><span /></span>
    <span><strong>Nebula</strong><small>AI CLOUD</small></span>
  </Link>
}

function Links({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation()
  return <div className="nebula-nav-list">
    <p className="nebula-nav-caption">WORKSPACE</p>
    {sections.map(({ label, to, marker }) => <NavLink key={to} to={to} end={to === '/'} onClick={onNavigate} aria-current={to === '/user/dashboard' && pathname.startsWith('/user/jobs/') ? 'page' : undefined} className={({ isActive }) => `nebula-nav-link${isActive || (to === '/user/dashboard' && pathname.startsWith('/user/jobs/')) ? ' is-active' : ''}`}>
      <span className="nebula-nav-marker" aria-hidden="true">{marker}</span>
      <span>{label}</span>
      <span className="nebula-nav-arrow" aria-hidden="true">↗</span>
    </NavLink>)}
  </div>
}

export default function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const current = location.pathname.startsWith('/user/jobs/') ? 'My jobs' : sections.find(({ to }) => to !== '/' && location.pathname.startsWith(to))?.label ?? 'Overview'

  return <>
    <aside className="nebula-sidebar" aria-label="Application sidebar">
      <Brand />
      <nav aria-label="Primary navigation"><Links /></nav>
      <div className="nebula-sidebar-bottom">
        <span className="nebula-sidebar-pulse" aria-hidden="true" />
        <span>Arbitrum Sepolia</span>
        <small>TESTNET</small>
      </div>
    </aside>
    <div className="nebula-mobile-header">
      <Brand />
      <button type="button" aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => setMobileOpen((open) => !open)} className="nebula-mobile-toggle">
        <span className="sr-only">{mobileOpen ? 'Close navigation' : 'Open navigation'}</span>
        <span aria-hidden="true">{mobileOpen ? 'Close' : 'Menu'}</span>
      </button>
    </div>
    {mobileOpen ? <nav id="mobile-navigation" aria-label="Mobile navigation" className="nebula-mobile-menu">
      <p className="nebula-mobile-current">Current · {current}</p>
      <Links onNavigate={() => setMobileOpen(false)} />
    </nav> : null}
  </>
}
