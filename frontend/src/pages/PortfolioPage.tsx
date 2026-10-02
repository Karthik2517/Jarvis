import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CircleDollarSign, Layers3, PieChart, TrendingUp, WalletCards } from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
import Metric from '../components/Metric'
import EmptyState from '../components/EmptyState'
import Pagination from '../components/Pagination'
import PageHeader from '../components/PageHeader'
import { money } from '../utils'

export default function PortfolioPage() {
  const {
    positions, orders, instruments, broker,
    resettingPaper, resetPaperPortfolio,
  } = useDashboard()
  const navigate = useNavigate()
  const [positionPage, setPositionPage] = useState(1)

  const openPositions = positions.filter(item => item.quantity !== 0)
  const positionPageSize = 5
  const positionsTotalPages = Math.max(1, Math.ceil(openPositions.length / positionPageSize))
  const paginatedPositions = openPositions.slice(
    (positionPage - 1) * positionPageSize,
    positionPage * positionPageSize,
  )
  const marketValue = openPositions.reduce((sum, item) => sum + Math.abs(item.market_value), 0)
  const investedValue = openPositions.reduce(
    (sum, item) => sum + Math.abs(item.average_price * item.quantity), 0,
  )
  const realizedPnl = positions.reduce((sum, item) => sum + item.realized_pnl, 0)
  const unrealizedPnl = openPositions.reduce((sum, item) => sum + item.unrealized_pnl, 0)
  const totalPnl = realizedPnl + unrealizedPnl
  const returnPercent = investedValue ? (totalPnl / investedValue) * 100 : 0
  const filledOrders = orders.filter(order => order.status === 'FILLED')
  const canResetPaper = broker.broker === 'PAPER'

  useEffect(() => {
    if (positionPage > positionsTotalPages) setPositionPage(positionsTotalPages)
  }, [positionPage, positionsTotalPages])

  function handleTrade(symbol: string) {
    // Navigate to overview with the symbol pre-selected via location state
    navigate('/overview', { state: { symbol } })
  }

  return (
    <>
      <PageHeader
        kicker="PORTFOLIO"
        title="Portfolio overview"
        subtitle="Track exposure, allocation, and performance in one place."
      />

      <section className="metrics portfolio-metrics">
        <Metric
          label="Current value"
          value={money.format(marketValue)}
          detail={`Cost basis ${money.format(investedValue)}`}
          icon={WalletCards}
        />
        <Metric
          label="Unrealized P&L"
          value={money.format(unrealizedPnl)}
          detail="Across open positions"
          icon={TrendingUp}
          tone={unrealizedPnl >= 0 ? 'positive' : 'negative'}
        />
        <Metric
          label="Total return"
          value={`${returnPercent >= 0 ? '+' : ''}${returnPercent.toFixed(2)}%`}
          detail={`${money.format(realizedPnl)} realized`}
          icon={CircleDollarSign}
          tone={returnPercent >= 0 ? 'positive' : 'negative'}
        />
      </section>

      <section className="portfolio-grid">
        <article className="card portfolio-summary">
          <div className="card-heading">
            <div><span className="kicker">DISTRIBUTION</span><h2>Portfolio allocation</h2></div>
            <div className="portfolio-actions">
              <PieChart size={19}/>
              {canResetPaper && (
                <button
                  className="reset-paper-button"
                  onClick={resetPaperPortfolio}
                  disabled={resettingPaper}
                >
                  {resettingPaper ? 'Resetting…' : 'Reset paper'}
                </button>
              )}
            </div>
          </div>
          {openPositions.length === 0
            ? <EmptyState text="Place your first order to build an allocation."/>
            : (
              <div className="allocation-list">
                {openPositions.map((position, index) => {
                  const allocation = marketValue
                    ? Math.abs(position.market_value) / marketValue * 100
                    : 0
                  return (
                    <div className="allocation-row" key={position.symbol}>
                      <div className="allocation-label">
                        <span className={`allocation-dot color-${index % 5}`}/>
                        <strong>{position.symbol}</strong>
                        <span>{allocation.toFixed(1)}%</span>
                      </div>
                      <div className="allocation-track">
                        <i className={`color-${index % 5}`} style={{ width: `${allocation}%` }}/>
                      </div>
                      <small>{money.format(Math.abs(position.market_value))}</small>
                    </div>
                  )
                })}
              </div>
            )
          }
          <div className="portfolio-total">
            <span>Total open exposure</span>
            <strong>{money.format(marketValue)}</strong>
          </div>
        </article>

        <article className="card portfolio-insight">
          <div className="card-heading">
            <div><span className="kicker">SNAPSHOT</span><h2>Trading activity</h2></div>
            <Layers3 size={19}/>
          </div>
          <div className="insight-list">
            <div>
              <span>Open positions</span>
              <strong>{openPositions.length}</strong>
              <small>Active NSE equities</small>
            </div>
            <div>
              <span>Filled orders</span>
              <strong>{filledOrders.length}</strong>
              <small>{filledOrders.filter(o => o.source === 'STRATEGY').length} from strategies</small>
            </div>
            <div>
              <span>Profitable positions</span>
              <strong>{openPositions.filter(p => p.total_pnl > 0).length}</strong>
              <small>Based on total P&amp;L</small>
            </div>
            <div>
              <span>Long / Short</span>
              <strong>
                {openPositions.filter(p => p.quantity > 0).length} / {openPositions.filter(p => p.quantity < 0).length}
              </strong>
              <small>Current direction mix</small>
            </div>
          </div>
        </article>
      </section>

      <section className="card holdings-card">
        <div className="card-heading">
          <div><span className="kicker">HOLDINGS</span><h2>Position details</h2></div>
          <span className="count">{openPositions.length}</span>
        </div>
        {openPositions.length === 0
          ? <EmptyState text="Your open holdings and P&L will appear here."/>
          : (
            <>
              <div className="table-wrap">
                <table>
                <thead>
                  <tr>
                    <th>Instrument</th><th>Direction</th><th>Quantity</th>
                    <th>Average</th><th>Last price</th><th>Invested</th>
                    <th>Current value</th><th>Unrealized</th><th>Realized</th>
                    <th>Total P&amp;L</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedPositions.map(position => {
                    const instrument = instruments.find(item => item.symbol === position.symbol)
                    const cost = Math.abs(position.average_price * position.quantity)
                    const positionReturn = cost ? position.total_pnl / cost * 100 : 0
                    return (
                      <tr key={position.symbol}>
                        <td>
                          <strong>{position.symbol}</strong>
                          <small>{instrument?.name || 'NSE equity'}</small>
                        </td>
                        <td>
                          <span className={`side ${position.quantity >= 0 ? 'buy' : 'sell'}`}>
                            {position.quantity >= 0 ? 'LONG' : 'SHORT'}
                          </span>
                        </td>
                        <td>{Math.abs(position.quantity)}</td>
                        <td>{money.format(position.average_price)}</td>
                        <td>{money.format(position.last_price)}</td>
                        <td>{money.format(cost)}</td>
                        <td>{money.format(Math.abs(position.market_value))}</td>
                        <td className={position.unrealized_pnl >= 0 ? 'gain' : 'loss'}>
                          {money.format(position.unrealized_pnl)}
                        </td>
                        <td className={position.realized_pnl >= 0 ? 'gain' : 'loss'}>
                          {money.format(position.realized_pnl)}
                        </td>
                        <td className={position.total_pnl >= 0 ? 'gain' : 'loss'}>
                          <strong>
                            {position.total_pnl >= 0 ? '+' : ''}{money.format(position.total_pnl)}
                          </strong>
                          <small>
                            {positionReturn >= 0 ? '+' : ''}{positionReturn.toFixed(2)}%
                          </small>
                        </td>
                        <td>
                          <button className="table-action" onClick={() => handleTrade(position.symbol)}>
                            Trade
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                </table>
              </div>
              <Pagination page={positionPage} totalPages={positionsTotalPages} onChange={setPositionPage}/>
            </>
          )
        }
      </section>
    </>
  )
}
