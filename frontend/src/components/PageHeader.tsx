import { useDashboard } from '../context/DashboardContext'
import { environmentLabel } from '../utils'

export default function PageHeader({
  kicker,
  title,
  subtitle,
}: {
  kicker: string
  title: string
  subtitle: string
}) {
  const { broker, switchBroker } = useDashboard()

  return (
    <div className="page-title">
      <div>
        <span className="kicker">{kicker}</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="broker-control">
        <div>
          <small>BROKER CONNECTION</small>
          <strong><i/>{broker.broker} · {broker.status.replace('_', ' ')}</strong>
        </div>
        <select
          value={broker.broker === 'UPSTOX' ? 'UPSTOX_LIVE' : broker.broker}
          onChange={e => switchBroker(e.target.value)}
        >
          <option value="PAPER">Paper</option>
          <option value="UPSTOX_SANDBOX">Upstox Sandbox</option>
          <option value="UPSTOX_LIVE">Upstox Live</option>
        </select>
      </div>
    </div>
  )
}
