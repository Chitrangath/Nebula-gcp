import { Outlet, useLocation } from 'react-router-dom'
import Navbar from './Navbar'
import WalletConnect from './WalletConnect'

const locations: Record<string, [string, string]> = {
  '/': ['Workspace', 'Overview'],
  '/network': ['Infrastructure', 'GPU network'],
  '/user/dashboard': ['AI user', 'My jobs'],
  '/user/submit': ['AI user', 'New job'],
  '/provider/dashboard': ['GPU provider', 'Console'],
  '/provider/register': ['GPU provider', 'Register node'],
}

export default function Layout() {
  const { pathname } = useLocation()
  const [group, page] = locations[pathname] ?? (pathname.startsWith('/user/jobs/') ? ['AI user', 'Job details'] : ['Workspace', 'Nebula'])

  return <div className="nebula-app">
    <a href="#main-content" className="nebula-skip-link">Skip to content</a>
    <Navbar />
    <div className="nebula-main-column">
      <header className="nebula-topbar">
        <div className="nebula-breadcrumb"><span>{group}</span><span aria-hidden="true">/</span><strong>{page}</strong></div>
        <div className="nebula-topbar-actions"><span className="nebula-chain-chip"><span aria-hidden="true" /> Arbitrum Sepolia</span><WalletConnect /></div>
      </header>
      <main id="main-content" className="nebula-page" tabIndex={-1}><Outlet /></main>
    </div>
  </div>
}
