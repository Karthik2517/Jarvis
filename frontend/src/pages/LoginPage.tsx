import { FormEvent, useState } from 'react'
import { Activity, Eye, EyeOff, Radio, ShieldCheck } from 'lucide-react'
import { api, ApiError } from '../api'

export default function LoginPage({ onLogin }: { onLogin: (email: string) => void }) {
  const [email, setEmail] = useState('jarvis@example.com')
  const [password, setPassword] = useState('jarvis1234')
  const [registering, setRegistering] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = registering
        ? await api.register(email, password)
        : await api.login(email, password)
      localStorage.setItem('jarvis_token', response.access_token)
      localStorage.setItem('jarvis_email', response.email)
      if ('strategy_api_key' in response && response.strategy_api_key) {
        localStorage.setItem('jarvis_new_api_key', String(response.strategy_api_key))
      }
      onLogin(response.email)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to connect to the API')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-visual">
        <div className="brand brand-large"><span className="brand-mark"><Activity size={23}/></span> JARVIS</div>
        <div className="hero-copy">
          <span className="eyebrow"><Radio size={14}/> PAPER MARKET ONLINE</span>
          <h1>Trade with clarity.<br/><em>Build with control.</em></h1>
          <p>A focused execution cockpit for manual orders and automated Python strategies.</p>
        </div>
        <div className="flow-strip"><span>Signal</span><i>→</i><span>Risk</span><i>→</i><span>Execute</span><i>→</i><span>Broker</span></div>
      </section>

      <section className="login-panel">
        <form className="auth-card" onSubmit={submit}>
          <div className="mobile-brand brand"><span className="brand-mark"><Activity size={20}/></span> JARVIS</div>
          <span className="kicker">SECURE ACCESS</span>
          <h2>{registering ? 'Create your account' : 'Welcome back'}</h2>
          <p>{registering ? 'Start with a private paper portfolio.' : 'Sign in to your trading workspace.'}</p>
          <label>
            Email address
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          </label>
          <label>
            Password
            <div className="password-field">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                minLength={8}
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={16}/> : <Eye size={16}/>}
              </button>
            </div>
          </label>
          {error && <div className="alert error">{error}</div>}
          <button className="primary wide" disabled={busy}>
            {busy ? 'Connecting…' : registering ? 'Create account' : 'Enter dashboard'}
          </button>
          <button
            className="text-button"
            type="button"
            onClick={() => { setRegistering(!registering); setError('') }}
          >
            {registering ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </button>
          {!registering && (
            <div className="demo-note"><ShieldCheck size={15}/> JARVIS credentials are pre-filled</div>
          )}
        </form>
      </section>
    </main>
  )
}
