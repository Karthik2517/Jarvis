import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Activity, BarChart3, LogOut, RefreshCw, ScanSearch, WalletCards, Zap } from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
import { formatIstTime } from '../utils'
import { api } from '../api'
import ProfilePanel from './ProfilePanel'

function profileNameKey(email: string) {
  return `jarvis_profile_name:${email.toLowerCase()}`
}

export default function Shell({
  email,
  onLogout,
}: {
  email: string
  onLogout: () => void
}) {
  const { broker, lastUpdated, refreshing, refreshNow } = useDashboard()
  const [loggingOut, setLoggingOut] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const [userName, setUserName] = useState(
    () => localStorage.getItem(profileNameKey(email)) || '',
  )
  const [joinedAt, setJoinedAt] = useState('')

  useEffect(() => {
    const cachedName = localStorage.getItem(profileNameKey(email))?.trim()
    api.getProfile()
      .then(p => {
        const persistedName = p.name.trim()
        if (!cachedName && persistedName) {
          localStorage.setItem(profileNameKey(email), persistedName)
          setUserName(persistedName)
        }
        setJoinedAt(p.created_at)
      })
      .catch(console.error)
  }, [email])

  function handleNameChange(name: string) {
    const persistedName = name.trim()
    localStorage.setItem(profileNameKey(email), persistedName)
    setUserName(persistedName)
  }

  function signOut() {
    if (loggingOut) return
    setLoggingOut(true)
    window.setTimeout(onLogout, 350)
  }

  return (
    <div className="app-shell">
      <header>
        <Link to="/overview" className="brand"><span className="brand-mark"><Activity size={20}/></span> JARVIS</Link>
        <div className="header-right">
          <div className="market-status">
            <span/> {broker.market_data_source === 'UPSTOX' ? 'UPSTOX FEED' : 'PAPER FEED'} ·{' '}
            {lastUpdated ? `UPDATED ${formatIstTime(lastUpdated)}` : 'LOADING'}
          </div>
          <button
            className={`icon-button refresh-button${refreshing ? ' refreshing' : ''}`}
            onClick={refreshNow}
            disabled={refreshing}
            title={refreshing ? 'Refreshing data…' : 'Refresh now'}
            aria-label={refreshing ? 'Refreshing data' : 'Refresh dashboard data'}
          >
            <RefreshCw size={17}/>
          </button>

          {/* Clickable user chip → opens profile panel */}
          <button
            className="user-chip"
            onClick={() => setProfileOpen(true)}
            title="Account settings"
            aria-label="Open account settings"
          >
            <span>{userName ? userName.slice(0, 1).toUpperCase() : email.slice(0, 1).toUpperCase()}</span>
            <div>{userName || email.split('@')[0]}</div>
          </button>

          <button
            className={`icon-button logout-button${loggingOut ? ' logging-out' : ''}`}
            onClick={signOut}
            disabled={loggingOut}
            title={loggingOut ? 'Signing out…' : 'Sign out'}
            aria-label={loggingOut ? 'Signing out' : 'Sign out'}
          >
            <LogOut size={17}/>
          </button>
        </div>
      </header>

      <nav>
        <NavLink to="/overview" className={({ isActive }) => isActive ? 'active' : undefined}>
          <BarChart3 size={17}/> Overview
        </NavLink>
        <NavLink to="/portfolio" className={({ isActive }) => isActive ? 'active' : undefined}>
          <WalletCards size={17}/> Portfolio
        </NavLink>
        <NavLink to="/scanner" className={({ isActive }) => isActive ? 'active' : undefined}>
          <ScanSearch size={17}/> Scanner
        </NavLink>
        <NavLink to="/strategies" className={({ isActive }) => isActive ? 'active' : undefined}>
          <Zap size={17}/> Strategies
        </NavLink>
      </nav>

      <main className="dashboard">
        <Outlet context={{ userName }} />
      </main>

      <ProfilePanel
        isOpen={profileOpen}
        email={email}
        userName={userName}
        joinedAt={joinedAt}
        onClose={() => setProfileOpen(false)}
        onNameChange={handleNameChange}
      />
    </div>
  )
}
