import { BarChart3 } from 'lucide-react'

export default function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty">
      <BarChart3 size={30}/>
      <strong>No activity yet</strong>
      <span>{text}</span>
    </div>
  )
}
