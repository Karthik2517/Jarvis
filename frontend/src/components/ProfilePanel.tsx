import { FormEvent, useEffect, useState } from 'react'
import { Eye, EyeOff, Lock, User, X } from 'lucide-react'
import { api, ApiError } from '../api'

interface Props {
  isOpen: boolean
  email: string
  userName: string
  joinedAt: string
  onClose: () => void
  onNameChange: (newName: string) => void
}

export default function ProfilePanel({ isOpen, email, userName, joinedAt, onClose, onNameChange }: Props) {

  // Display name form
  const [name, setName] = useState('')
  const [nameBusy, setNameBusy] = useState(false)
  const [nameNotice, setNameNotice] = useState('')
  const [nameError, setNameError] = useState('')

  // Change password form
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showCurrentPw, setShowCurrentPw] = useState(false)
  const [showNewPw, setShowNewPw] = useState(false)
  const [pwBusy, setPwBusy] = useState(false)
  const [pwNotice, setPwNotice] = useState('')
  const [pwError, setPwError] = useState('')

  // Load profile when panel opens
  useEffect(() => {
    if (!isOpen) return
    setName(userName)
    // Reset password form
    setCurrentPw(''); setNewPw(''); setConfirmPw('')
    setPwNotice(''); setPwError('')
    setShowCurrentPw(false); setShowNewPw(false)
    setNameNotice(''); setNameError('')
  }, [isOpen, userName])

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  async function submitName(e: FormEvent) {
    e.preventDefault()
    setNameBusy(true); setNameError(''); setNameNotice('')
    try {
      const profile = await api.updateProfile({ name })
      onNameChange(profile.name)
      setNameNotice('Display name saved')
    } catch (err) {
      setNameError(err instanceof ApiError ? err.message : 'Could not save name')
    } finally { setNameBusy(false) }
  }

  async function submitPassword(e: FormEvent) {
    e.preventDefault()
    if (newPw !== confirmPw) { setPwError('New passwords do not match'); return }
    setPwBusy(true); setPwError(''); setPwNotice('')
    try {
      await api.updateProfile({ new_password: newPw, current_password: currentPw })
      setPwNotice('Password changed successfully')
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
    } catch (err) {
      setPwError(err instanceof ApiError ? err.message : 'Could not change password')
    } finally { setPwBusy(false) }
  }

  const initial = email.slice(0, 1).toUpperCase()
  const memberSince = joinedAt
    ? new Intl.DateTimeFormat('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Kolkata',
      }).format(new Date(joinedAt.includes('T') ? joinedAt + 'Z' : joinedAt + 'T00:00:00Z'))
    : ''

  return (
    <>
      <div className={`profile-overlay${isOpen ? ' open' : ''}`} onClick={onClose} aria-hidden="true" />

      <aside
        className={`profile-panel${isOpen ? ' open' : ''}`}
        aria-label="Account settings"
        aria-modal="true"
        role="dialog"
      >
        {/* Header */}
        <div className="profile-panel-header">
          <strong>Account settings</strong>
          <button className="icon-button" onClick={onClose} aria-label="Close panel"><X size={17}/></button>
        </div>

        {/* Identity */}
        <div className="profile-avatar-section">
          <div className="profile-avatar">{userName ? userName.slice(0, 1).toUpperCase() : initial}</div>
          <div>
            <strong>{userName || 'User'}</strong>
            <small style={{ display: 'block', color: 'var(--text-muted, #888)' }}>{email}</small>
            {memberSince && <small>Member since {memberSince}</small>}
          </div>
        </div>

        {/* ── Display name ── */}
        <div className="profile-section-divider"><span>Display name</span></div>

        <form className="profile-form" onSubmit={submitName}>
          <label>
            <span><User size={12}/> Name</span>
            <input
              type="text"
              value={name}
              onChange={e => { setName(e.target.value); setNameNotice('') }}
              placeholder="Enter your name"
              maxLength={80}
              autoComplete="name"
            />
          </label>
          {nameError && <div className="alert error">{nameError}</div>}
          {nameNotice && <div className="alert success">{nameNotice}</div>}
          <button className="primary" disabled={nameBusy}>
            {nameBusy ? 'Saving…' : 'Save name'}
          </button>
        </form>

        {/* ── Change password ── */}
        <div className="profile-section-divider"><span>Change password</span></div>

        <form className="profile-form" onSubmit={submitPassword} noValidate>
          <label>
            <span><Lock size={12}/> Current password</span>
            <div className="password-field">
              <input
                type={showCurrentPw ? 'text' : 'password'}
                value={currentPw}
                onChange={e => setCurrentPw(e.target.value)}
                autoComplete="current-password"
                required
              />
              <button type="button" onClick={() => setShowCurrentPw(v => !v)} aria-label={showCurrentPw ? 'Hide' : 'Show'}>
                {showCurrentPw ? <EyeOff size={14}/> : <Eye size={14}/>}
              </button>
            </div>
          </label>
          <label>
            <span><Lock size={12}/> New password</span>
            <div className="password-field">
              <input
                type={showNewPw ? 'text' : 'password'}
                value={newPw}
                onChange={e => setNewPw(e.target.value)}
                minLength={8}
                autoComplete="new-password"
                required
              />
              <button type="button" onClick={() => setShowNewPw(v => !v)} aria-label={showNewPw ? 'Hide' : 'Show'}>
                {showNewPw ? <EyeOff size={14}/> : <Eye size={14}/>}
              </button>
            </div>
          </label>
          <label>
            <span><Lock size={12}/> Confirm new password</span>
            <input
              type="password"
              value={confirmPw}
              onChange={e => setConfirmPw(e.target.value)}
              minLength={8}
              autoComplete="new-password"
              required
            />
          </label>
          {pwError && <div className="alert error">{pwError}</div>}
          {pwNotice && <div className="alert success">{pwNotice}</div>}
          <button className="primary" disabled={pwBusy || !currentPw || !newPw || !confirmPw}>
            {pwBusy ? 'Saving…' : 'Change password'}
          </button>
        </form>
      </aside>
    </>
  )
}
