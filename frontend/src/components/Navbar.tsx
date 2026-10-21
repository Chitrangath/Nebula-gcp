import { Link } from 'react-router-dom'
import WalletConnect from './WalletConnect'

export default function Navbar() {
  return (
    <nav className="bg-white shadow-sm">
      <div className="container mx-auto px-4">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="text-xl font-bold text-primary-600">
            Nebula AI Cloud
          </Link>
          <div className="flex items-center gap-4">
            <Link to="/provider/dashboard" className="text-gray-600 hover:text-gray-900">
              Provider
            </Link>
            <Link to="/user/dashboard" className="text-gray-600 hover:text-gray-900">
              User
            </Link>
            <WalletConnect />
          </div>
        </div>
      </div>
    </nav>
  )
}
