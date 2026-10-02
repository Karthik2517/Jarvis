import type { WalletCards } from 'lucide-react'

export default function Metric({
  label, value, detail, icon: Icon, tone = '',
}: {
  label: string
  value: string
  detail: string
  icon: typeof WalletCards
  tone?: string
}) {
  return (
    <article className={`metric ${tone}`}>
      <div className="metric-icon"><Icon size={19}/></div>
      <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
    </article>
  )
}
