import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useOutletContext } from 'react-router-dom'
import {
  Activity, ArrowDownRight, ArrowUpRight, CircleDollarSign, RefreshCw,
  Search, ShieldCheck, WalletCards,
} from 'lucide-react'
import { api, ApiError } from '../api'
import { useDashboard } from '../context/DashboardContext'
import type { Instrument, Side } from '../types'
import Metric from '../components/Metric'
import Pagination from '../components/Pagination'
import EmptyState from '../components/EmptyState'
import PageHeader from '../components/PageHeader'
import { apiDate, environmentLabel, formatIstTime, money } from '../utils'

export default function OverviewPage({ email }: { email: string }) {
  const { userName } = useOutletContext<{ userName: string }>()
  const {
    instruments, positions, orders, broker, load,
    addInstrument, setNotice: setGlobalNotice, setError: setGlobalError,
  } = useDashboard()

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
  const [positionsPage, setPositionsPage] = useState(1)
  const [ordersPage, setOrdersPage] = useState(1)

  const location = useLocation()
  const navigate = useNavigate()

  // Handle "Trade" button from Portfolio page — pre-select the instrument
  useEffect(() => {
    const symbol = (location.state as { symbol?: string } | null)?.symbol
    if (!symbol) return
    const instrument = instruments.find(item => item.symbol === symbol)
    if (instrument) setSelected(instrument)
    // Clear location state so it doesn't persist on refresh
    navigate('/overview', { replace: true, state: null })
  }, [location.state, instruments, navigate])

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

  brokerModeRef.current = broker.broker
  selectedSymbolRef.current = selected?.symbol || null

  const openPositions = positions.filter(item => item.quantity !== 0)
  const pageSize = 5
  const positionsTotalPages = Math.max(1, Math.ceil(openPositions.length / pageSize))
  const ordersTotalPages = Math.max(1, Math.ceil(orders.length / pageSize))
  const currentPositionsPage = Math.min(positionsPage, positionsTotalPages)
  const currentOrdersPage = Math.min(ordersPage, ordersTotalPages)
  const visiblePositions = openPositions.slice(
    (currentPositionsPage - 1) * pageSize, currentPositionsPage * pageSize,
  )
  const visibleOrders = orders.slice(
    (currentOrdersPage - 1) * pageSize, currentOrdersPage * pageSize,
  )
  const totalPnl = positions.reduce((sum, item) => sum + item.total_pnl, 0)
  const exposure = openPositions.reduce((sum, item) => sum + Math.abs(item.market_value), 0)
  const parsedQuantity = Number(quantity)
  const validQuantity = Number.isInteger(parsedQuantity) && parsedQuantity > 0
  const currentEnvironment = environmentLabel(broker.broker)

  async function trade(side: Side) {
    if (!selected) return
    if (!validQuantity) { setError('Enter a positive whole-number quantity'); return }
    const isLiveOrder = broker.broker === 'UPSTOX_LIVE' || broker.broker === 'UPSTOX'
    const orderBroker = broker.broker
    const orderSymbol = selected.symbol
    if (
      isLiveOrder &&
      !window.confirm(
        `LIVE ORDER\n\n${side} ${parsedQuantity} ${selected.symbol} at market.\n\nThis can use real funds. Continue?`,
      )
    ) return
    setBusy(true); setError(''); setNotice('')
    try {
      const order = await api.placeOrder(selected.symbol, side, parsedQuantity, isLiveOrder)
      const isCurrentContext =
        brokerModeRef.current === orderBroker && selectedSymbolRef.current === orderSymbol
      if (order.status === 'REJECTED' && isCurrentContext) {
        setError(order.rejection_reason || 'Order rejected')
      } else if (isCurrentContext) {
        setError('')
        setNotice(`${side} ${parsedQuantity} ${selected.symbol} filled at ${money.format(order.average_price || 0)}`)
        setQuantity('1')
        setPositionsPage(1)
        setOrdersPage(1)
      }
      // The order has already succeeded. A delayed dashboard refresh must not
      // replace the success message with a misleading trade error.
      await load(true)
    } catch (err) {
      if (brokerModeRef.current === orderBroker && selectedSymbolRef.current === orderSymbol) {
        setError(err instanceof Error ? err.message : 'Order failed')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        kicker="TRADING DESK"
        title={`Good day, ${userName || email.split('@')[0]}`}
        subtitle="One execution path. Manual or automated."
      />

      <section className="metrics">
        <Metric
          label="Portfolio P&L"
          value={money.format(totalPnl)}
          detail="Realized + unrealized"
          icon={CircleDollarSign}
          tone={totalPnl >= 0 ? 'positive' : 'negative'}
        />
        <Metric
          label="Open exposure"
          value={money.format(exposure)}
          detail={`${openPositions.length} active position${openPositions.length === 1 ? '' : 's'}`}
          icon={WalletCards}
        />
        <Metric
          label="Orders today"
          value={String(orders.length)}
          detail={`${orders.filter(o => o.status === 'FILLED').length} filled`}
          icon={Activity}
        />
      </section>

      {(notice || error) && (
        <div className={`alert ${error ? 'error' : 'success'}`}>{error || notice}</div>
      )}

      <section className="workspace-grid">
        <article className="card order-ticket">
          <div className="card-heading">
            <div><span className="kicker">ORDER ENTRY</span><h2>Place market order</h2></div>
            <span className="live-pill">PAPER</span>
          </div>

          <div className="instrument-search">
            <label className="search-box">
              <Search size={18}/>
              <input
                autoComplete="off"
                placeholder="Search NSE equities — e.g. RELIANCE"
                value={query}
                onFocus={() => query.trim().length >= 2 && setSearchOpen(true)}
                onChange={e => { setQuery(e.target.value); setError(''); setNotice('') }}
              />
              {searching && <RefreshCw className="search-spinner" size={15}/>}
            </label>
            {searchOpen && query.trim().length >= 2 && (
              <div className="instrument-list">
                {searchError
                  ? <div className="search-message error-text">{searchError}</div>
                  : !searching && searchResults.length === 0
                    ? <div className="search-message">No NSE equities found</div>
                    : searchResults.map(item => (
                      <button
                        className={
                          selected?.instrument_key === item.instrument_key &&
                          selected?.symbol === item.symbol
                            ? 'selected'
                            : ''
                        }
                        key={item.instrument_key || item.symbol}
                        onClick={() => {
                          setSelected(item)
                          setQuery('')
                          setSearchOpen(false)
                          setError('')
                          setNotice('')
                          addInstrument(item)
                        }}
                      >
                        <div><strong>{item.symbol}</strong><span>{item.name}</span></div>
                        <div>
                          <b>{item.price > 0 ? money.format(item.price) : 'Quote unavailable'}</b>
                          <small>{item.exchange} · {currentEnvironment}</small>
                        </div>
                      </button>
                    ))
                }
              </div>
            )}
          </div>

          {selected && (
            <div className="selected-instrument">
              <div>
                <span>{selected.exchange} · {currentEnvironment}</span>
                <h3>{selected.symbol}</h3>
                <p>{selected.name}</p>
              </div>
              <div>
                <small>LAST PRICE</small>
                <strong>{selected.price > 0 ? money.format(selected.price) : 'Unavailable'}</strong>
                {typeof selected.change_percent === 'number' && (
                  <em className={selected.change_percent >= 0 ? 'gain' : 'loss'}>
                    {selected.change_percent >= 0 ? '+' : ''}{selected.change_percent.toFixed(2)}%
                  </em>
                )}
              </div>
            </div>
          )}

          <label className="quantity">
            Quantity
            <div>
              <button
                type="button"
                onClick={() => setQuantity(String(Math.max(1, (validQuantity ? parsedQuantity : 1) - 1)))}
              >−</button>
              <input
                type="number"
                inputMode="numeric"
                min="1"
                step="1"
                value={quantity}
                placeholder="1"
                onChange={e => setQuantity(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setQuantity(String((validQuantity ? parsedQuantity : 0) + 1))}
              >+</button>
            </div>
          </label>

          <div className="order-value">
            <span>Estimated value</span>
            <strong>{money.format((selected?.price || 0) * (validQuantity ? parsedQuantity : 0))}</strong>
          </div>

          <div className="trade-buttons">
            <button
              className="buy"
              disabled={busy || !selected || selected.price <= 0 || !validQuantity}
              onClick={() => trade('BUY')}
            >
              <ArrowUpRight size={18}/> BUY
            </button>
            <button
              className="sell"
              disabled={busy || !selected || selected.price <= 0 || !validQuantity}
              onClick={() => trade('SELL')}
            >
              <ArrowDownRight size={18}/> SELL
            </button>
          </div>
          <p className="risk-note">
            <ShieldCheck size={15}/> Order passes through quantity and notional risk checks before execution.
          </p>
        </article>

        <article className="card positions-card">
          <div className="card-heading">
            <div><span className="kicker">PORTFOLIO</span><h2>Open positions</h2></div>
            <span className="count">{openPositions.length}</span>
          </div>
          {openPositions.length === 0
            ? <EmptyState text="Your filled orders will appear here."/>
            : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Instrument</th><th>Qty</th><th>Avg.</th><th>LTP</th><th>P&amp;L</th></tr></thead>
                  <tbody>
                    {visiblePositions.map(position => (
                      <tr key={position.symbol}>
                        <td><strong>{position.symbol}</strong><small>NSE · EQ</small></td>
                        <td>{position.quantity}</td>
                        <td>{money.format(position.average_price)}</td>
                        <td>{money.format(position.last_price)}</td>
                        <td className={position.total_pnl >= 0 ? 'gain' : 'loss'}>
                          {position.total_pnl >= 0 ? '+' : ''}{money.format(position.total_pnl)}
                        </td>
                      </tr>
                    ))}
                    {Array.from({ length: pageSize - visiblePositions.length }, (_, index) => (
                      <tr className="placeholder-row" aria-hidden="true" key={`pos-placeholder-${index}`}>
                        <td><strong>&nbsp;</strong><small>&nbsp;</small></td>
                        <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pagination
                  page={currentPositionsPage}
                  totalPages={positionsTotalPages}
                  onChange={setPositionsPage}
                />
              </div>
            )
          }
        </article>
      </section>

      <section className="card orders-card">
        <div className="card-heading">
          <div><span className="kicker">EXECUTION LOG</span><h2>Recent orders</h2></div>
          <small>Latest 100 orders</small>
        </div>
        {orders.length === 0
          ? <EmptyState text="No orders submitted yet."/>
          : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th><th>Instrument</th><th>Side</th>
                    <th>Filled / Qty</th><th>Source</th><th>Fill price</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleOrders.map(order => (
                    <tr key={order.id}>
                      <td>{formatIstTime(apiDate(order.created_at))}</td>
                      <td>
                        <strong>{order.symbol}</strong>
                        {(order.broker_order_id || order.rejection_reason) && (
                          <small>{order.broker_order_id || order.rejection_reason}</small>
                        )}
                      </td>
                      <td><span className={`side ${order.side.toLowerCase()}`}>{order.side}</span></td>
                      <td>{order.filled_quantity} / {order.quantity}</td>
                      <td>{order.source === 'STRATEGY' ? order.strategy_name || 'Strategy' : 'Manual'}</td>
                      <td>{order.average_price !== null ? money.format(order.average_price) : '—'}</td>
                      <td><span className={`status ${order.status.toLowerCase()}`}>{order.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pagination page={currentOrdersPage} totalPages={ordersTotalPages} onChange={setOrdersPage}/>
            </div>
          )
        }
      </section>
    </>
  )
}
