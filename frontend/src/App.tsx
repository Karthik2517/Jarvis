import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3, Check, CircleDollarSign,
  Clipboard, Code2, Eye, EyeOff, KeyRound, Layers3, LogOut, Pause, PieChart, Play, Plus,
  Radio, RefreshCw, ScanSearch, Search, ShieldCheck, TrendingUp, WalletCards, Zap,
} from 'lucide-react'
import { api, ApiError } from './api'
import ScannerView from './ScannerView'
import type { BrokerStatus, Instrument, Order, Position, Side, Strategy } from './types'

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
const istTime = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit',
})
const istDateTime = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit',
})

function apiDate(value: string) {
  return new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`)
}

function formatIstTime(value: Date) { return `${istTime.format(value)} IST` }
function formatIstDateTime(value: string) { return `${istDateTime.format(apiDate(value))} IST` }

function environmentLabel(broker: string) {
  if (broker === 'UPSTOX_SANDBOX') return 'UPSTOX SANDBOX'
  if (broker === 'UPSTOX' || broker === 'UPSTOX_LIVE') return 'UPSTOX LIVE'
  return 'PAPER'
}

function Login({ onLogin }: { onLogin: (email: string) => void }) {
  const [email, setEmail] = useState('jarvis@example.com')
  const [password, setPassword] = useState('jarvis1234')
  const [registering, setRegistering] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const response = registering ? await api.register(email, password) : await api.login(email, password)
      localStorage.setItem('jarvis_token', response.access_token)
      localStorage.setItem('jarvis_email', response.email)
      if ('strategy_api_key' in response && response.strategy_api_key) {
        localStorage.setItem('jarvis_new_api_key', String(response.strategy_api_key))
      }
      onLogin(response.email)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to connect to the API')
    } finally { setBusy(false) }
  }

  return <main className="login-page">
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
        <label>Email address<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>
        <label>Password<div className="password-field"><input type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} minLength={8} required /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={16}/> : <Eye size={16}/>}</button></div></label>
        {error && <div className="alert error">{error}</div>}
        <button className="primary wide" disabled={busy}>{busy ? 'Connecting…' : registering ? 'Create account' : 'Enter dashboard'}</button>
        <button className="text-button" type="button" onClick={() => { setRegistering(!registering); setError('') }}>
          {registering ? 'Already have an account? Sign in' : 'New here? Create an account'}
        </button>
        {!registering && <div className="demo-note"><ShieldCheck size={15}/> JARVIS credentials are pre-filled</div>}
      </form>
    </section>
  </main>
}

function Metric({ label, value, detail, icon: Icon, tone = '' }: { label: string; value: string; detail: string; icon: typeof WalletCards; tone?: string }) {
  return <article className={`metric ${tone}`}>
    <div className="metric-icon"><Icon size={19}/></div>
    <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
  </article>
}

function Pagination({ page, totalPages, onChange }: { page: number; totalPages: number; onChange: (page: number) => void }) {
  if (totalPages <= 1) return null
  return <div className="pagination">
    <button type="button" disabled={page === 1} onClick={() => onChange(page - 1)}>Previous</button>
    <span>Page {page} of {totalPages}</span>
    <button type="button" disabled={page === totalPages} onClick={() => onChange(page + 1)}>Next</button>
  </div>
}

function PortfolioView({
  positions,
  orders,
  instruments,
  onTrade,
  onResetPaper,
  resettingPaper,
  canResetPaper,
}: {
  positions: Position[]
  orders: Order[]
  instruments: Instrument[]
  onTrade: (symbol: string) => void
  onResetPaper: () => void
  resettingPaper: boolean
  canResetPaper: boolean
}) {
  const openPositions = positions.filter(item => item.quantity !== 0)
  const marketValue = openPositions.reduce((sum, item) => sum + Math.abs(item.market_value), 0)
  const investedValue = openPositions.reduce((sum, item) => sum + Math.abs(item.average_price * item.quantity), 0)
  const realizedPnl = positions.reduce((sum, item) => sum + item.realized_pnl, 0)
  const unrealizedPnl = openPositions.reduce((sum, item) => sum + item.unrealized_pnl, 0)
  const totalPnl = realizedPnl + unrealizedPnl
  const returnPercent = investedValue ? (totalPnl / investedValue) * 100 : 0
  const filledOrders = orders.filter(order => order.status === 'FILLED')

  return <>
    <section className="metrics portfolio-metrics">
      <Metric label="Current value" value={money.format(marketValue)} detail={`Cost basis ${money.format(investedValue)}`} icon={WalletCards}/>
      <Metric label="Unrealized P&L" value={money.format(unrealizedPnl)} detail="Across open positions" icon={TrendingUp} tone={unrealizedPnl >= 0 ? 'positive' : 'negative'}/>
      <Metric label="Total return" value={`${returnPercent >= 0 ? '+' : ''}${returnPercent.toFixed(2)}%`} detail={`${money.format(realizedPnl)} realized`} icon={CircleDollarSign} tone={returnPercent >= 0 ? 'positive' : 'negative'}/>
    </section>

    <section className="portfolio-grid">
      <article className="card portfolio-summary">
        <div className="card-heading"><div><span className="kicker">DISTRIBUTION</span><h2>Portfolio allocation</h2></div><div className="portfolio-actions"><PieChart size={19}/>{canResetPaper && <button className="reset-paper-button" onClick={onResetPaper} disabled={resettingPaper}>{resettingPaper ? 'Resetting…' : 'Reset paper'}</button>}</div></div>
        {openPositions.length === 0 ? <EmptyState text="Place your first order to build an allocation."/> : <div className="allocation-list">
          {openPositions.map((position, index) => {
            const allocation = marketValue ? Math.abs(position.market_value) / marketValue * 100 : 0
            return <div className="allocation-row" key={position.symbol}>
              <div className="allocation-label"><span className={`allocation-dot color-${index % 5}`}/><strong>{position.symbol}</strong><span>{allocation.toFixed(1)}%</span></div>
              <div className="allocation-track"><i className={`color-${index % 5}`} style={{ width: `${allocation}%` }}/></div>
              <small>{money.format(Math.abs(position.market_value))}</small>
            </div>
          })}
        </div>}
        <div className="portfolio-total"><span>Total open exposure</span><strong>{money.format(marketValue)}</strong></div>
      </article>

      <article className="card portfolio-insight">
        <div className="card-heading"><div><span className="kicker">SNAPSHOT</span><h2>Trading activity</h2></div><Layers3 size={19}/></div>
        <div className="insight-list">
          <div><span>Open positions</span><strong>{openPositions.length}</strong><small>Active NSE equities</small></div>
          <div><span>Filled orders</span><strong>{filledOrders.length}</strong><small>{filledOrders.filter(order => order.source === 'STRATEGY').length} from strategies</small></div>
          <div><span>Profitable positions</span><strong>{openPositions.filter(position => position.total_pnl > 0).length}</strong><small>Based on total P&L</small></div>
          <div><span>Long / Short</span><strong>{openPositions.filter(position => position.quantity > 0).length} / {openPositions.filter(position => position.quantity < 0).length}</strong><small>Current direction mix</small></div>
        </div>
      </article>
    </section>

    <section className="card holdings-card">
      <div className="card-heading"><div><span className="kicker">HOLDINGS</span><h2>Position details</h2></div><span className="count">{openPositions.length}</span></div>
      {openPositions.length === 0 ? <EmptyState text="Your open holdings and P&L will appear here."/> : <div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Direction</th><th>Quantity</th><th>Average</th><th>Last price</th><th>Invested</th><th>Current value</th><th>Unrealized</th><th>Realized</th><th>Total P&L</th><th></th></tr></thead><tbody>
        {openPositions.map(position => {
          const instrument = instruments.find(item => item.symbol === position.symbol)
          const cost = Math.abs(position.average_price * position.quantity)
          const positionReturn = cost ? position.total_pnl / cost * 100 : 0
          return <tr key={position.symbol}>
            <td><strong>{position.symbol}</strong><small>{instrument?.name || 'NSE equity'}</small></td>
            <td><span className={`side ${position.quantity >= 0 ? 'buy' : 'sell'}`}>{position.quantity >= 0 ? 'LONG' : 'SHORT'}</span></td>
            <td>{Math.abs(position.quantity)}</td><td>{money.format(position.average_price)}</td><td>{money.format(position.last_price)}</td>
            <td>{money.format(cost)}</td><td>{money.format(Math.abs(position.market_value))}</td>
            <td className={position.unrealized_pnl >= 0 ? 'gain' : 'loss'}>{money.format(position.unrealized_pnl)}</td>
            <td className={position.realized_pnl >= 0 ? 'gain' : 'loss'}>{money.format(position.realized_pnl)}</td>
            <td className={position.total_pnl >= 0 ? 'gain' : 'loss'}><strong>{position.total_pnl >= 0 ? '+' : ''}{money.format(position.total_pnl)}</strong><small>{positionReturn >= 0 ? '+' : ''}{positionReturn.toFixed(2)}%</small></td>
            <td><button className="table-action" onClick={() => onTrade(position.symbol)}>Trade</button></td>
          </tr>
        })}
      </tbody></table></div>}
    </section>
  </>
}

function StrategiesView({
  strategies,
  orders,
  apiKey,
  onCreate,
  onToggle,
  onRotateKey,
}: {
  strategies: Strategy[]
  orders: Order[]
  apiKey: string
  onCreate: (name: string, description: string) => Promise<void>
  onToggle: (strategy: Strategy) => Promise<void>
  onRotateKey: () => Promise<void>
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [working, setWorking] = useState(false)
  const [copied, setCopied] = useState(false)
  const strategyOrders = orders.filter(order => order.source === 'STRATEGY')
  const signals = strategies.reduce((sum, strategy) => sum + strategy.signal_count, 0)
  const code = `import httpx

httpx.post(
    "http://localhost:8000/api/signals",
    headers={"X-Strategy-Key": "${apiKey || 'YOUR_STRATEGY_API_KEY'}"},
    json={
        "strategy_name": "momentum-v1",
        "symbol": "RELIANCE",
        "side": "BUY",
        "quantity": 10,
    },
).raise_for_status()`

  async function submit(event: FormEvent) {
    event.preventDefault(); setWorking(true)
    try {
      await onCreate(name, description)
      setName(''); setDescription(''); setShowForm(false)
    } catch {
      // Parent surfaces the API error in the shared dashboard alert.
    } finally { setWorking(false) }
  }

  async function copyCode() {
    await navigator.clipboard.writeText(code)
    setCopied(true); window.setTimeout(() => setCopied(false), 1600)
  }

  return <>
    <section className="metrics strategy-metrics">
      <Metric label="Active strategies" value={String(strategies.filter(item => item.status === 'ACTIVE').length)} detail={`${strategies.length} registered`} icon={Zap}/>
      <Metric label="Signals received" value={String(signals)} detail="Accepted by Signal API" icon={Radio}/>
      <Metric label="Strategy orders" value={String(strategyOrders.length)} detail={`${strategyOrders.filter(order => order.status === 'FILLED').length} filled`} icon={Activity}/>
    </section>

    <section className="strategy-grid">
      <article className="card strategies-card">
        <div className="card-heading strategies-heading"><div><span className="kicker">AUTOMATION</span><h2>Connected strategies</h2></div><button className="secondary-button" onClick={() => setShowForm(value => !value)}><Plus size={14}/> Add strategy</button></div>
        {showForm && <form className="strategy-form" onSubmit={submit}>
          <label>Strategy name<input value={name} onChange={event => setName(event.target.value)} placeholder="momentum-v1" minLength={2} required/></label>
          <label>Description<input value={description} onChange={event => setDescription(event.target.value)} placeholder="Optional notes about this strategy" maxLength={240}/></label>
          <button className="primary" disabled={working}>{working ? 'Adding…' : 'Register strategy'}</button>
        </form>}
        {strategies.length === 0 ? <EmptyState text="Register a strategy here or send your first API signal."/> : <div className="strategy-list">
          {strategies.map(strategy => <div className="strategy-item" key={strategy.id}>
            <div className={`strategy-glyph ${strategy.status.toLowerCase()}`}><Code2 size={18}/></div>
            <div className="strategy-copy"><div><strong>{strategy.name}</strong><span className={`status ${strategy.status === 'ACTIVE' ? 'filled' : 'pending'}`}>{strategy.status}</span></div><p>{strategy.description || 'Python signal strategy'}</p><small>{strategy.signal_count} signal{strategy.signal_count === 1 ? '' : 's'} · {strategy.last_signal_at ? `Last ${formatIstDateTime(strategy.last_signal_at)}` : 'Waiting for first signal'}</small></div>
            <button className="strategy-toggle" onClick={() => onToggle(strategy)} title={strategy.status === 'ACTIVE' ? 'Pause strategy' : 'Resume strategy'}>{strategy.status === 'ACTIVE' ? <Pause size={15}/> : <Play size={15}/>}</button>
          </div>)}
        </div>}
      </article>

      <article className="card api-card">
        <div className="card-heading"><div><span className="kicker">SIGNAL API</span><h2>Connect Python</h2></div><KeyRound size={19}/></div>
        <p>Send orders into the same risk and execution pipeline used by the dashboard.</p>
        <div className="api-key-box"><span>STRATEGY API KEY</span><code>{apiKey ? `${apiKey.slice(0, 8)}••••••••••••${apiKey.slice(-4)}` : 'Generate a key to connect'}</code><button onClick={onRotateKey}>{apiKey ? 'Rotate key' : 'Generate key'}</button></div>
        {apiKey && <div className="key-warning"><ShieldCheck size={14}/> This key is shown only in this browser session. Store it securely.</div>}
        <div className="code-heading"><span>Python example</span><button onClick={copyCode}>{copied ? <Check size={13}/> : <Clipboard size={13}/>} {copied ? 'Copied' : 'Copy'}</button></div>
        <pre><code>{code}</code></pre>
      </article>
    </section>

    <section className="card orders-card strategy-orders">
      <div className="card-heading"><div><span className="kicker">SIGNAL ACTIVITY</span><h2>Recent strategy orders</h2></div><small>{strategyOrders.length} total</small></div>
      {strategyOrders.length === 0 ? <EmptyState text="Orders generated by Python signals will appear here."/> : <div className="table-wrap"><table><thead><tr><th>Time</th><th>Strategy</th><th>Instrument</th><th>Side</th><th>Quantity</th><th>Fill price</th><th>Status</th></tr></thead><tbody>
        {strategyOrders.map(order => <tr key={order.id}><td>{formatIstDateTime(order.created_at)}</td><td><strong>{order.strategy_name}</strong></td><td>{order.symbol}</td><td><span className={`side ${order.side.toLowerCase()}`}>{order.side}</span></td><td>{order.quantity}</td><td>{order.average_price ? money.format(order.average_price) : '—'}</td><td><span className={`status ${order.status.toLowerCase()}`}>{order.status}</span></td></tr>)}
      </tbody></table></div>}
    </section>
  </>
}

function Dashboard({ email, onLogout }: { email: string; onLogout: () => void }) {
  const [activeView, setActiveView] = useState<'overview' | 'portfolio' | 'strategies' | 'scanner'>('overview')
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [strategyApiKey, setStrategyApiKey] = useState(() => localStorage.getItem('jarvis_new_api_key') || '')
  const [broker, setBroker] = useState<BrokerStatus>({ broker: 'PAPER', status: 'CONNECTED' })
  const [selected, setSelected] = useState<Instrument | null>(null)
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Instrument[]>([])
  const [searching, setSearching] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchError, setSearchError] = useState('')
  const searchSequence = useRef(0)
  const brokerModeRef = useRef('PAPER')
  const selectedSymbolRef = useRef<string | null>(null)
  const [quantity, setQuantity] = useState('1')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [resettingPaper, setResettingPaper] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [positionsPage, setPositionsPage] = useState(1)
  const [ordersPage, setOrdersPage] = useState(1)

  const load = useCallback(async (silent = false) => {
    try {
      // Reconcile broker orders first so positions reflect any newly confirmed fills.
      const allOrders = await api.orders()
      const [allInstruments, allPositions, brokerStatus, allStrategies] = await Promise.all([
        api.instruments(), api.positions(true), api.broker(), api.strategies(),
      ])
      setInstruments(allInstruments); setPositions(allPositions); setOrders(allOrders); setBroker(brokerStatus); setStrategies(allStrategies)
      setLastUpdated(new Date())
    } catch (err) {
      if (err instanceof ApiError && err.message.toLowerCase().includes('token')) onLogout()
      else if (!silent) setError(err instanceof Error ? err.message : 'Could not load dashboard')
    }
  }, [onLogout])

  async function refreshNow() {
    if (refreshing) return
    setRefreshing(true)
    try {
      // Keep the visual feedback visible even when the API responds immediately.
      await Promise.all([load(), new Promise(resolve => window.setTimeout(resolve, 500))])
    } finally {
      setRefreshing(false)
    }
  }

  function signOut() {
    if (loggingOut) return
    setLoggingOut(true)
    window.setTimeout(onLogout, 350)
  }

  useEffect(() => {
    // Background polling should never show a trade error after a successful
    // order. The manual refresh control still reports a real refresh failure.
    load(true)
    const refreshTimer = window.setInterval(() => { void load(true) }, 10_000)
    return () => window.clearInterval(refreshTimer)
  }, [load])

  useEffect(() => {
    const term = query.trim()
    if (term.length < 2) {
      setSearchResults([]); setSearching(false); setSearchError('')
      return
    }
    const sequence = ++searchSequence.current
    setSearching(true); setSearchError(''); setSearchOpen(true)
    const timer = window.setTimeout(async () => {
      try {
        const results = await api.instruments(term)
        if (sequence === searchSequence.current) setSearchResults(results)
      } catch (err) {
        if (sequence === searchSequence.current) {
          setSearchResults([])
          setSearchError(err instanceof Error ? err.message : 'Instrument search failed')
        }
      } finally {
        if (sequence === searchSequence.current) setSearching(false)
      }
    }, 320)
    return () => window.clearTimeout(timer)
  }, [query])

  const openPositions = positions.filter(item => item.quantity !== 0)
  const pageSize = 5
  const positionsTotalPages = Math.max(1, Math.ceil(openPositions.length / pageSize))
  const ordersTotalPages = Math.max(1, Math.ceil(orders.length / pageSize))
  const currentPositionsPage = Math.min(positionsPage, positionsTotalPages)
  const currentOrdersPage = Math.min(ordersPage, ordersTotalPages)
  const visiblePositions = openPositions.slice((currentPositionsPage - 1) * pageSize, currentPositionsPage * pageSize)
  const visibleOrders = orders.slice((currentOrdersPage - 1) * pageSize, currentOrdersPage * pageSize)
  const totalPnl = positions.reduce((sum, item) => sum + item.total_pnl, 0)
  const exposure = openPositions.reduce((sum, item) => sum + Math.abs(item.market_value), 0)
  const parsedQuantity = Number(quantity)
  const validQuantity = Number.isInteger(parsedQuantity) && parsedQuantity > 0
  const currentEnvironment = environmentLabel(broker.broker)
  brokerModeRef.current = broker.broker
  selectedSymbolRef.current = selected?.symbol || null

  useEffect(() => {
    // An order error belongs to the symbol and execution environment that
    // produced it. Do not carry it into a new stock or broker selection.
    setError('')
    setNotice('')
  }, [broker.broker, selected?.symbol])

  useEffect(() => {
    setPositionsPage(1)
    setOrdersPage(1)
  }, [broker.broker])

  async function trade(side: Side) {
    if (!selected) return
    if (!validQuantity) {
      setError('Enter a positive whole-number quantity')
      return
    }
    const isLiveOrder = broker.broker === 'UPSTOX_LIVE' || broker.broker === 'UPSTOX'
    const orderBroker = broker.broker
    const orderSymbol = selected.symbol
    if (isLiveOrder && !window.confirm(
      `LIVE ORDER\n\n${side} ${parsedQuantity} ${selected.symbol} at market.\n\nThis can use real funds. Continue?`
    )) return
    setBusy(true); setError(''); setNotice('')
    try {
      const order = await api.placeOrder(selected.symbol, side, parsedQuantity, isLiveOrder)
      const isCurrentOrderContext = brokerModeRef.current === orderBroker && selectedSymbolRef.current === orderSymbol
      if (order.status === 'REJECTED' && isCurrentOrderContext) setError(order.rejection_reason || 'Order rejected')
      else {
        if (isCurrentOrderContext) {
          setError('')
          setNotice(`${side} ${parsedQuantity} ${selected.symbol} filled at ${money.format(order.average_price || 0)}`)
          setQuantity('1')
          setPositionsPage(1)
          setOrdersPage(1)
        }
      }
      // The order has already succeeded. A delayed dashboard refresh must not
      // replace the success message with a misleading trade error.
      await load(true)
    } catch (err) {
      if (brokerModeRef.current === orderBroker && selectedSymbolRef.current === orderSymbol) {
        setError(err instanceof Error ? err.message : 'Order failed')
      }
    }
    finally { setBusy(false) }
  }

  async function switchBroker(name: string) {
    try {
      const response = await api.connectBroker(name)
      setBroker(response); setNotice(response.message); setError('')
      await load(true)
    } catch (err) { setError(err instanceof Error ? err.message : 'Broker update failed') }
  }

  async function createStrategy(name: string, description: string) {
    try { await api.createStrategy(name, description); setNotice(`Strategy ${name} registered`); setError(''); await load(true) }
    catch (err) { setError(err instanceof Error ? err.message : 'Could not create strategy'); throw err }
  }

  async function toggleStrategy(strategy: Strategy) {
    try {
      const nextStatus = strategy.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'
      await api.updateStrategy(strategy.id, nextStatus); setNotice(`${strategy.name} ${nextStatus.toLowerCase()}`); setError(''); await load(true)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update strategy') }
  }

  async function rotateStrategyKey() {
    try {
      const response = await api.rotateStrategyKey()
      localStorage.setItem('jarvis_new_api_key', response.strategy_api_key)
      setStrategyApiKey(response.strategy_api_key); setNotice(response.message); setError('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not generate API key') }
  }

  async function resetPaperPortfolio() {
    if (resettingPaper || !window.confirm('Reset the PAPER portfolio? This will permanently remove all paper orders and positions. Sandbox and live data will not be affected.')) return
    setResettingPaper(true); setError(''); setNotice('')
    try {
      const response = await api.resetPaperPortfolio()
      setNotice(`${response.message} (${response.orders_removed} orders, ${response.positions_removed} positions removed)`)
      await load(true)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not reset paper portfolio') }
    finally { setResettingPaper(false) }
  }

  return <div className="app-shell">
    <header>
      <div className="brand"><span className="brand-mark"><Activity size={20}/></span> JARVIS</div>
      <div className="header-right">
        <div className="market-status"><span/> {broker.market_data_source === 'UPSTOX' ? 'UPSTOX FEED' : 'PAPER FEED'} · {lastUpdated ? `UPDATED ${formatIstTime(lastUpdated)}` : 'LOADING'}</div>
        <button className={`icon-button refresh-button${refreshing ? ' refreshing' : ''}`} onClick={refreshNow} disabled={refreshing} title={refreshing ? 'Refreshing data…' : 'Refresh now'} aria-label={refreshing ? 'Refreshing data' : 'Refresh dashboard data'}><RefreshCw size={17}/></button>
        <div className="user-chip"><span>{email.slice(0, 1).toUpperCase()}</span><div>{email}<small>Trader</small></div></div>
        <button className={`icon-button logout-button${loggingOut ? ' logging-out' : ''}`} onClick={signOut} disabled={loggingOut} title={loggingOut ? 'Signing out…' : 'Sign out'} aria-label={loggingOut ? 'Signing out' : 'Sign out'}><LogOut size={17}/></button>
      </div>
    </header>

    <nav><button className={activeView === 'overview' ? 'active' : ''} onClick={() => setActiveView('overview')}><BarChart3 size={17}/> Overview</button><button className={activeView === 'portfolio' ? 'active' : ''} onClick={() => setActiveView('portfolio')}><WalletCards size={17}/> Portfolio</button><button className={activeView === 'scanner' ? 'active' : ''} onClick={() => setActiveView('scanner')}><ScanSearch size={17}/> Scanner</button><button className={activeView === 'strategies' ? 'active' : ''} onClick={() => setActiveView('strategies')}><Zap size={17}/> Strategies</button></nav>

    <main className="dashboard">
      <div className="page-title"><div><span className="kicker">{activeView === 'overview' ? 'TRADING DESK' : activeView === 'portfolio' ? 'PORTFOLIO' : activeView === 'scanner' ? 'MARKET DISCOVERY' : 'AUTOMATION'}</span><h1>{activeView === 'overview' ? `Good day, ${email.split('@')[0]}` : activeView === 'portfolio' ? 'Portfolio overview' : activeView === 'scanner' ? 'Equity scanner' : 'Strategy control center'}</h1><p>{activeView === 'overview' ? 'One execution path. Manual or automated.' : activeView === 'portfolio' ? 'Track exposure, allocation, and performance in one place.' : activeView === 'scanner' ? 'Find NSE equities that match technical conditions.' : 'Connect Python strategies and control their execution access.'}</p></div>
        <div className="broker-control"><div><small>BROKER CONNECTION</small><strong><i/>{broker.broker} · {broker.status.replace('_', ' ')}</strong></div>
          <select disabled={busy} value={broker.broker === 'UPSTOX' ? 'UPSTOX_LIVE' : broker.broker} onChange={e => switchBroker(e.target.value)}><option value="PAPER">Paper</option><option value="UPSTOX_SANDBOX">Upstox Sandbox</option><option value="UPSTOX_LIVE">Upstox Live</option></select>
        </div>
      </div>

      {activeView === 'overview' ? <><section className="metrics">
        <Metric label="Portfolio P&L" value={money.format(totalPnl)} detail="Realized + unrealized" icon={CircleDollarSign} tone={totalPnl >= 0 ? 'positive' : 'negative'}/>
        <Metric label="Open exposure" value={money.format(exposure)} detail={`${openPositions.length} active position${openPositions.length === 1 ? '' : 's'}`} icon={WalletCards}/>
        <Metric label="Orders today" value={String(orders.length)} detail={`${orders.filter(o => o.status === 'FILLED').length} filled`} icon={Activity}/>
      </section>

      {(notice || error) && <div className={`alert ${error ? 'error' : 'success'}`}>{error || notice}</div>}

      <section className="workspace-grid">
        <article className="card order-ticket">
          <div className="card-heading"><div><span className="kicker">ORDER ENTRY</span><h2>Place market order</h2></div><span className="live-pill">PAPER</span></div>
          <div className="instrument-search">
            <label className="search-box"><Search size={18}/><input autoComplete="off" placeholder="Search NSE equities — e.g. RELIANCE" value={query} onFocus={() => query.trim().length >= 2 && setSearchOpen(true)} onChange={e => { setQuery(e.target.value); setError(''); setNotice('') }}/>{searching && <RefreshCw className="search-spinner" size={15}/>}</label>
            {searchOpen && query.trim().length >= 2 && <div className="instrument-list">
              {searchError ? <div className="search-message error-text">{searchError}</div> : !searching && searchResults.length === 0 ? <div className="search-message">No NSE equities found</div> : searchResults.map(item => <button className={selected?.instrument_key === item.instrument_key && selected?.symbol === item.symbol ? 'selected' : ''} key={item.instrument_key || item.symbol} onClick={() => {
                setSelected(item); setQuery(''); setSearchOpen(false); setError(''); setNotice('')
                setInstruments(current => current.some(existing => existing.symbol === item.symbol) ? current : [...current, item])
              }}>
                <div><strong>{item.symbol}</strong><span>{item.name}</span></div><div><b>{item.price > 0 ? money.format(item.price) : 'Quote unavailable'}</b><small>{item.exchange} · {currentEnvironment}</small></div>
              </button>)}
            </div>}
          </div>
          {selected && <div className="selected-instrument"><div><span>{selected.exchange} · {currentEnvironment}</span><h3>{selected.symbol}</h3><p>{selected.name}</p></div><div><small>LAST PRICE</small><strong>{selected.price > 0 ? money.format(selected.price) : 'Unavailable'}</strong>{typeof selected.change_percent === 'number' && <em className={selected.change_percent >= 0 ? 'gain' : 'loss'}>{selected.change_percent >= 0 ? '+' : ''}{selected.change_percent.toFixed(2)}%</em>}</div></div>}
          <label className="quantity">Quantity<div><button type="button" onClick={() => setQuantity(String(Math.max(1, (validQuantity ? parsedQuantity : 1) - 1)))}>−</button><input type="number" inputMode="numeric" min="1" step="1" value={quantity} placeholder="1" onChange={e => setQuantity(e.target.value)}/><button type="button" onClick={() => setQuantity(String((validQuantity ? parsedQuantity : 0) + 1))}>+</button></div></label>
          <div className="order-value"><span>Estimated value</span><strong>{money.format((selected?.price || 0) * (validQuantity ? parsedQuantity : 0))}</strong></div>
          <div className="trade-buttons"><button className="buy" disabled={busy || !selected || selected.price <= 0 || !validQuantity} onClick={() => trade('BUY')}><ArrowUpRight size={18}/> BUY</button><button className="sell" disabled={busy || !selected || selected.price <= 0 || !validQuantity} onClick={() => trade('SELL')}><ArrowDownRight size={18}/> SELL</button></div>
          <p className="risk-note"><ShieldCheck size={15}/> Order passes through quantity and notional risk checks before execution.</p>
        </article>

        <article className="card positions-card">
          <div className="card-heading"><div><span className="kicker">PORTFOLIO</span><h2>Open positions</h2></div><span className="count">{openPositions.length}</span></div>
          {openPositions.length === 0 ? <EmptyState text="Your filled orders will appear here."/> : <div className="table-wrap"><table><thead><tr><th>Instrument</th><th>Qty</th><th>Avg.</th><th>LTP</th><th>P&L</th></tr></thead><tbody>
            {visiblePositions.map(position => <tr key={position.symbol}><td><strong>{position.symbol}</strong><small>NSE · EQ</small></td><td>{position.quantity}</td><td>{money.format(position.average_price)}</td><td>{money.format(position.last_price)}</td><td className={position.total_pnl >= 0 ? 'gain' : 'loss'}>{position.total_pnl >= 0 ? '+' : ''}{money.format(position.total_pnl)}</td></tr>)}
            {Array.from({ length: pageSize - visiblePositions.length }, (_, index) => <tr className="placeholder-row" aria-hidden="true" key={`position-placeholder-${index}`}><td><strong>&nbsp;</strong><small>&nbsp;</small></td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>)}
          </tbody></table><Pagination page={currentPositionsPage} totalPages={positionsTotalPages} onChange={setPositionsPage}/></div>}
        </article>
      </section>

      <section className="card orders-card">
        <div className="card-heading"><div><span className="kicker">EXECUTION LOG</span><h2>Recent orders</h2></div><small>Latest 100 orders</small></div>
        {orders.length === 0 ? <EmptyState text="No orders submitted yet."/> : <div className="table-wrap"><table><thead><tr><th>Time</th><th>Instrument</th><th>Side</th><th>Filled / Qty</th><th>Source</th><th>Fill price</th><th>Status</th></tr></thead><tbody>
          {visibleOrders.map(order => <tr key={order.id}>
            <td>{formatIstTime(apiDate(order.created_at))}</td>
            <td><strong>{order.symbol}</strong>{(order.broker_order_id || order.rejection_reason) && <small>{order.broker_order_id || order.rejection_reason}</small>}</td>
            <td><span className={`side ${order.side.toLowerCase()}`}>{order.side}</span></td>
            <td>{order.filled_quantity} / {order.quantity}</td>
            <td>{order.source === 'STRATEGY' ? order.strategy_name || 'Strategy' : 'Manual'}</td>
            <td>{order.average_price !== null ? money.format(order.average_price) : '—'}</td>
            <td><span className={`status ${order.status.toLowerCase()}`}>{order.status}</span></td>
          </tr>)}
        </tbody></table><Pagination page={currentOrdersPage} totalPages={ordersTotalPages} onChange={setOrdersPage}/></div>}
      </section>
      </> : activeView === 'portfolio' ? <PortfolioView positions={positions} orders={orders} instruments={instruments} onResetPaper={resetPaperPortfolio} resettingPaper={resettingPaper} canResetPaper={broker.broker === 'PAPER'} onTrade={symbol => {
        setSelected(instruments.find(item => item.symbol === symbol) || null)
        setActiveView('overview')
      }}/> : activeView === 'scanner' ? <ScannerView/> : <StrategiesView strategies={strategies} orders={orders} apiKey={strategyApiKey} onCreate={createStrategy} onToggle={toggleStrategy} onRotateKey={rotateStrategyKey}/>}
    </main>
  </div>
}

function EmptyState({ text }: { text: string }) { return <div className="empty"><BarChart3 size={30}/><strong>No activity yet</strong><span>{text}</span></div> }

export default function App() {
  const [email, setEmail] = useState(() => localStorage.getItem('jarvis_email') || '')
  const logout = useCallback(() => { localStorage.removeItem('jarvis_token'); localStorage.removeItem('jarvis_email'); setEmail('') }, [])
  useEffect(() => {
    window.addEventListener('jarvis:unauthorized', logout)
    return () => window.removeEventListener('jarvis:unauthorized', logout)
  }, [logout])
  return email && localStorage.getItem('jarvis_token') ? <Dashboard email={email} onLogout={logout}/> : <Login onLogin={setEmail}/>
}
