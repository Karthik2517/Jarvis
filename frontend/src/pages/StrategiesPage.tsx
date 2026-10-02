import { FormEvent, useState } from 'react'
import {
  Activity, Check, Clipboard, Code2, KeyRound, Pause, Play, Plus, Radio, ShieldCheck, Zap,
} from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
import Metric from '../components/Metric'
import EmptyState from '../components/EmptyState'
import PageHeader from '../components/PageHeader'
import { formatIstDateTime, money } from '../utils'

export default function StrategiesPage() {
  const {
    strategies, orders, strategyApiKey,
    createStrategy, toggleStrategy, rotateStrategyKey,
  } = useDashboard()

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
    headers={"X-Strategy-Key": "${strategyApiKey || 'YOUR_STRATEGY_API_KEY'}"},
    json={
        "strategy_name": "momentum-v1",
        "symbol": "RELIANCE",
        "side": "BUY",
        "quantity": 10,
    },
).raise_for_status()`

  async function submit(event: FormEvent) {
    event.preventDefault()
    setWorking(true)
    try {
      await createStrategy(name, description)
      setName('')
      setDescription('')
      setShowForm(false)
    } catch {
      // Parent surfaces the API error via the shared dashboard alert in context.
    } finally {
      setWorking(false)
    }
  }

  async function copyCode() {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <>
      <PageHeader
        kicker="AUTOMATION"
        title="Strategy control center"
        subtitle="Connect Python strategies and control their execution access."
      />

      <section className="metrics strategy-metrics">
        <Metric
          label="Active strategies"
          value={String(strategies.filter(item => item.status === 'ACTIVE').length)}
          detail={`${strategies.length} registered`}
          icon={Zap}
        />
        <Metric
          label="Signals received"
          value={String(signals)}
          detail="Accepted by Signal API"
          icon={Radio}
        />
        <Metric
          label="Strategy orders"
          value={String(strategyOrders.length)}
          detail={`${strategyOrders.filter(o => o.status === 'FILLED').length} filled`}
          icon={Activity}
        />
      </section>

      <section className="strategy-grid">
        <article className="card strategies-card">
          <div className="card-heading strategies-heading">
            <div><span className="kicker">AUTOMATION</span><h2>Connected strategies</h2></div>
            <button className="secondary-button" onClick={() => setShowForm(v => !v)}>
              <Plus size={14}/> Add strategy
            </button>
          </div>

          {showForm && (
            <form className="strategy-form" onSubmit={submit}>
              <label>
                Strategy name
                <input
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="momentum-v1"
                  minLength={2}
                  required
                />
              </label>
              <label>
                Description
                <input
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Optional notes about this strategy"
                  maxLength={240}
                />
              </label>
              <button className="primary" disabled={working}>
                {working ? 'Adding…' : 'Register strategy'}
              </button>
            </form>
          )}

          {strategies.length === 0
            ? <EmptyState text="Register a strategy here or send your first API signal."/>
            : (
              <div className="strategy-list">
                {strategies.map(strategy => (
                  <div className="strategy-item" key={strategy.id}>
                    <div className={`strategy-glyph ${strategy.status.toLowerCase()}`}>
                      <Code2 size={18}/>
                    </div>
                    <div className="strategy-copy">
                      <div>
                        <strong>{strategy.name}</strong>
                        <span className={`status ${strategy.status === 'ACTIVE' ? 'filled' : 'pending'}`}>
                          {strategy.status}
                        </span>
                      </div>
                      <p>{strategy.description || 'Python signal strategy'}</p>
                      <small>
                        {strategy.signal_count} signal{strategy.signal_count === 1 ? '' : 's'} ·{' '}
                        {strategy.last_signal_at
                          ? `Last ${formatIstDateTime(strategy.last_signal_at)}`
                          : 'Waiting for first signal'
                        }
                      </small>
                    </div>
                    <button
                      className="strategy-toggle"
                      onClick={() => toggleStrategy(strategy)}
                      title={strategy.status === 'ACTIVE' ? 'Pause strategy' : 'Resume strategy'}
                    >
                      {strategy.status === 'ACTIVE' ? <Pause size={15}/> : <Play size={15}/>}
                    </button>
                  </div>
                ))}
              </div>
            )
          }
        </article>

        <article className="card api-card">
          <div className="card-heading">
            <div><span className="kicker">SIGNAL API</span><h2>Connect Python</h2></div>
            <KeyRound size={19}/>
          </div>
          <p>Send orders into the same risk and execution pipeline used by the dashboard.</p>
          <div className="api-key-box">
            <span>STRATEGY API KEY</span>
            <code>
              {strategyApiKey
                ? `${strategyApiKey.slice(0, 8)}••••••••••••${strategyApiKey.slice(-4)}`
                : 'Generate a key to connect'
              }
            </code>
            <button onClick={rotateStrategyKey}>
              {strategyApiKey ? 'Rotate key' : 'Generate key'}
            </button>
          </div>
          {strategyApiKey && (
            <div className="key-warning">
              <ShieldCheck size={14}/> This key is shown only in this browser session. Store it securely.
            </div>
          )}
          <div className="code-heading">
            <span>Python example</span>
            <button onClick={copyCode}>
              {copied ? <Check size={13}/> : <Clipboard size={13}/>} {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <pre><code>{code}</code></pre>
        </article>
      </section>

      <section className="card orders-card strategy-orders">
        <div className="card-heading">
          <div><span className="kicker">SIGNAL ACTIVITY</span><h2>Recent strategy orders</h2></div>
          <small>{strategyOrders.length} total</small>
        </div>
        {strategyOrders.length === 0
          ? <EmptyState text="Orders generated by Python signals will appear here."/>
          : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th><th>Strategy</th><th>Instrument</th>
                    <th>Side</th><th>Quantity</th><th>Fill price</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {strategyOrders.map(order => (
                    <tr key={order.id}>
                      <td>{formatIstDateTime(order.created_at)}</td>
                      <td><strong>{order.strategy_name}</strong></td>
                      <td>{order.symbol}</td>
                      <td><span className={`side ${order.side.toLowerCase()}`}>{order.side}</span></td>
                      <td>{order.quantity}</td>
                      <td>{order.average_price ? money.format(order.average_price) : '—'}</td>
                      <td><span className={`status ${order.status.toLowerCase()}`}>{order.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </section>
    </>
  )
}
