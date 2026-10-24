import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import ProviderDashboard from './pages/provider/Dashboard'
import RegisterNode from './pages/provider/RegisterNode'
import UserDashboard from './pages/user/Dashboard'
import SubmitJob from './pages/user/SubmitJob'
import JobDetail from './pages/user/JobDetail'
import Network from './pages/Network'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="provider/dashboard" element={<ProviderDashboard />} />
          <Route path="provider/register" element={<RegisterNode />} />
          <Route path="user/dashboard" element={<UserDashboard />} />
          <Route path="user/submit" element={<SubmitJob />} />
          <Route path="user/jobs/:id" element={<JobDetail />} />
          <Route path="network" element={<Network />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
