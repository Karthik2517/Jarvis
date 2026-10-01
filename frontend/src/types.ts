export type Side = 'BUY' | 'SELL'

export interface Instrument {
  symbol: string
  name: string
  exchange: string
  price: number
  instrument_key?: string | null
  source?: 'UPSTOX' | 'PAPER'
  previous_close?: number
  change_percent?: number
}

export interface Order {
  id: number
  execution_mode: string
  broker_order_id: string | null
  symbol: string
  side: Side
  quantity: number
  filled_quantity: number
  product: string
  instrument_key: string | null
  source: 'MANUAL' | 'STRATEGY'
  strategy_name: string | null
  status: 'FILLED' | 'REJECTED' | 'PENDING'
  average_price: number | null
  rejection_reason: string | null
  created_at: string
}

export interface Position {
  execution_mode: string
  symbol: string
  quantity: number
  average_price: number
  last_price: number
  market_value: number
  realized_pnl: number
  unrealized_pnl: number
  total_pnl: number
}

export interface BrokerStatus {
  broker: string
  status: string
  market_data_source?: string
}

export interface Strategy {
  id: number
  name: string
  description: string
  status: 'ACTIVE' | 'PAUSED'
  signal_count: number
  last_signal_at: string | null
  created_at: string
}
