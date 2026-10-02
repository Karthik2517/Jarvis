import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { DashboardProvider } from './context/DashboardContext'
import Shell from './components/Shell'
import LoginPage from './pages/LoginPage'
import OverviewPage from './pages/OverviewPage'
import PortfolioPage from './pages/PortfolioPage'
import ScannerPage from './pages/ScannerPage'
import StrategiesPage from './pages/StrategiesPage'

export default function App() {
  const [email, setEmail] = useState(() => localStorage.getItem('jarvis_email') || '')
  const navigate = useNavigate()

  const logout = useCallback(() => {
    localStorage.removeItem('jarvis_token')
    localStorage.removeItem('jarvis_email')
    setEmail('')
    navigate('/login', { replace: true })
  }, [navigate])

  useEffect(() => {
    window.addEventListener('jarvis:unauthorized', logout)
    return () => window.removeEventListener('jarvis:unauthorized', logout)
  }, [logout])

  const isAuthenticated = !!(email && localStorage.getItem('jarvis_token'))

  return (
    <Routes>
      {/* Public: login page */}
      <Route
        path="/login"
        element={
          isAuthenticated
            ? <Navigate to="/overview" replace />
            : (
              <LoginPage
                onLogin={e => {
                  setEmail(e)
                  navigate('/overview', { replace: true })
                }}
              />
            )
        }
      />

      {/* Protected: shell layout with nested pages */}
      <Route
        path="/"
        element={
          isAuthenticated
            ? (
              <DashboardProvider onLogout={logout} email={email}>
                <Shell email={email} onLogout={logout} />
              </DashboardProvider>
            )
            : <Navigate to="/login" replace />
        }
      >
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="overview" element={<OverviewPage email={email} />} />
        <Route path="portfolio" element={<PortfolioPage />} />
        <Route path="scanner" element={<ScannerPage />} />
        <Route path="strategies" element={<StrategiesPage />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to={isAuthenticated ? '/overview' : '/login'} replace />} />
    </Routes>
  )
}
