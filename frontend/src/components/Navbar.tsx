import { useState } from 'react'
import { Link } from 'react-router-dom'
import WalletConnect from './WalletConnect'

export default function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const links = [['Network', '/network'], ['Provider', '/provider/dashboard'], ['User', '/user/dashboard']] as const

  return (
    <nav className="bg-white shadow-sm">
      <div className="container mx-auto px-4">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="text-lg font-bold text-primary-600 sm:text-xl focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2">
            Nebula AI Cloud
          </Link>
          <div className="hidden items-center gap-4 md:flex">
            {links.map(([label, to]) => <Link key={to} to={to} className="text-gray-600 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2">{label}</Link>)}
            <WalletConnect />
          </div>
          <button type="button" aria-expanded={mobileOpen} aria-controls="mobile-navigation" onClick={() => setMobileOpen((open) => !open)} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-gray-300 px-3 font-semibold text-gray-800 focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-2 md:hidden">
            <span className="sr-only">{mobileOpen ? 'Close navigation' : 'Open navigation'}</span>
            <span aria-hidden="true">{mobileOpen ? 'Close' : 'Menu'}</span>
          </button>
        </div>
        {mobileOpen ? <div id="mobile-navigation" className="space-y-2 border-t border-gray-200 py-4 md:hidden">
          {links.map(([label, to]) => <Link key={to} to={to} onClick={() => setMobileOpen(false)} className="flex min-h-11 items-center rounded-lg px-3 font-semibold text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-600">{label}</Link>)}
          <div className="flex min-h-11 items-center px-3"><WalletConnect /></div>
        </div> : null}
      </div>
    </nav>
  )
}
