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

export type ScannerField =
  | 'price' | 'volume' | 'avg_volume_20' | 'volume_ratio'
  | 'sma20' | 'sma50' | 'sma200' | 'rsi14'
  | 'prior_52w_high' | 'prior_52w_low'
  | 'breakout_percent' | 'breakdown_percent'

export type ScannerOperator = '>' | '>=' | '<' | '<=' | '=='
export type RankDirection = 'asc' | 'desc'

export interface ScannerOperand {
  value?: number
  field?: ScannerField
  multiplier?: number
}

export interface ScannerCondition {
  left: ScannerField
  operator: ScannerOperator
  right: ScannerOperand
}

export interface ScannerPreset {
  key: string
  name: string
  description: string
  minimum_history: number
  rank_field: ScannerField
  rank_direction: RankDirection
  conditions: ScannerCondition[]
}

export interface ScannerCatalog {
  presets: ScannerPreset[]
  fields: ScannerField[]
  operators: ScannerOperator[]
}

export interface ScannerIndicators {
  price: number
  volume: number
  sma20: number | null
  sma50: number | null
  sma200: number | null
  avg_volume_20: number | null
  volume_ratio: number | null
  rsi14: number | null
  prior_52w_high: number | null
  prior_52w_low: number | null
  breakout_percent: number | null
  breakdown_percent: number | null
}

export interface ScannerResultItem {
  rank: number
  rank_value: number
  instrument_key: string
  symbol: string
  name: string
  exchange: string
  data_as_of: string
  indicators: ScannerIndicators
}

export interface ScannerPage {
  scanner_key: string
  page: number
  page_size: number
  total_pages: number
  total_matches: number
  total_instruments: number
  evaluated: number
  skipped_count: number
  skip_reasons: Record<string, number>
  has_previous: boolean
  has_next: boolean
  items: ScannerResultItem[]
}

export interface ScannerRunRequest {
  preset_key?: string
  conditions?: ScannerCondition[]
  rank_field?: ScannerField
  rank_direction?: RankDirection
  page: number
  page_size: number
  refresh: boolean
}

export interface SavedScanner {
  id: number
  name: string
  preset_key: string | null
  conditions: ScannerCondition[]
  rank_field: ScannerField
  rank_direction: RankDirection
  created_at: string
  updated_at: string
}

export interface ScannerAlert {
  id: number
  saved_scanner_id: number
  saved_scanner_name: string
  name: string
  minimum_matches: number
  enabled: boolean
  last_checked_at: string | null
  last_triggered_at: string | null
  created_at: string
}

export interface ScannerAlertEvent {
  id: number
  alert_id: number
  alert_name: string
  match_count: number
  symbols: string[]
  data_as_of: string | null
  is_read: boolean
  created_at: string
}

export interface ScannerAlertEvaluation {
  triggered: boolean
  scanner_key: string
  match_count: number
  event: ScannerAlertEvent | null
}
