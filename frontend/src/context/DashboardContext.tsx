import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { BrokerStatus, Instrument, Order, Position, Strategy } from '../types'

interface DashboardState {
  instruments: Instrument[]
  positions: Position[]
  orders: Order[]
  strategies: Strategy[]
  broker: BrokerStatus
  strategyApiKey: string
  lastUpdated: Date | null
  refreshing: boolean
  resettingPaper: boolean
  notice: string
  error: string
  load: (silent?: boolean) => Promise<void>
  refreshNow: () => Promise<void>
  switchBroker: (name: string) => Promise<void>
  createStrategy: (name: string, description: string) => Promise<void>
  toggleStrategy: (strategy: Strategy) => Promise<void>
  rotateStrategyKey: () => Promise<void>
  resetPaperPortfolio: () => Promise<void>
  addInstrument: (instrument: Instrument) => void
  setNotice: (notice: string) => void
  setError: (error: string) => void
}

const DashboardContext = createContext<DashboardState | null>(null)

export function useDashboard() {
  const ctx = useContext(DashboardContext)
  if (!ctx) throw new Error('useDashboard must be used within DashboardProvider')
  return ctx
}

export function DashboardProvider({
  onLogout,
  children,
}: {
  onLogout: () => void
  children: React.ReactNode
}) {
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [strategyApiKey, setStrategyApiKey] = useState(
    () => localStorage.getItem('jarvis_new_api_key') || '',
  )
  const [broker, setBroker] = useState<BrokerStatus>({ broker: 'PAPER', status: 'CONNECTED' })
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [resettingPaper, setResettingPaper] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async (silent = false) => {
    try {
      // Reconcile broker orders first so positions reflect any newly confirmed fills.
      const allOrders = await api.orders()
      const [allInstruments, allPositions, brokerStatus, allStrategies] = await Promise.all([
        api.instruments(), api.positions(true), api.broker(), api.strategies(),
      ])
      setInstruments(allInstruments)
      setPositions(allPositions)
      setOrders(allOrders)
      setBroker(brokerStatus)
      setStrategies(allStrategies)
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

  useEffect(() => {
    // Background polling should never show a stale error.
    load(true)
    const timer = window.setInterval(() => { void load(true) }, 10_000)
    return () => window.clearInterval(timer)
  }, [load])

  async function switchBroker(name: string) {
    try {
      const response = await api.connectBroker(name)
      setBroker(response)
      setNotice(response.message)
      setError('')
      await load(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Broker update failed')
    }
  }

  async function createStrategy(name: string, description: string) {
    try {
      await api.createStrategy(name, description)
      setNotice(`Strategy ${name} registered`)
      setError('')
      await load(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create strategy')
      throw err
    }
  }

  async function toggleStrategy(strategy: Strategy) {
    try {
      const nextStatus = strategy.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'
      await api.updateStrategy(strategy.id, nextStatus)
      setNotice(`${strategy.name} ${nextStatus.toLowerCase()}`)
      setError('')
      await load(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update strategy')
    }
  }

  async function rotateStrategyKey() {
    try {
      const response = await api.rotateStrategyKey()
      localStorage.setItem('jarvis_new_api_key', response.strategy_api_key)
      setStrategyApiKey(response.strategy_api_key)
      setNotice(response.message)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate API key')
    }
  }

  async function resetPaperPortfolio() {
    if (
      resettingPaper ||
      !window.confirm(
        'Reset the PAPER portfolio? This will permanently remove all paper orders and positions. Sandbox and live data will not be affected.',
      )
    ) return
    setResettingPaper(true)
    setError('')
    setNotice('')
    try {
      const response = await api.resetPaperPortfolio()
      setNotice(
        `${response.message} (${response.orders_removed} orders, ${response.positions_removed} positions removed)`,
      )
      await load(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reset paper portfolio')
    } finally {
      setResettingPaper(false)
    }
  }

  function addInstrument(instrument: Instrument) {
    setInstruments(current =>
      current.some(existing => existing.symbol === instrument.symbol)
        ? current
        : [...current, instrument],
    )
  }

  return (
    <DashboardContext.Provider value={{
      instruments, positions, orders, strategies, broker,
      strategyApiKey, lastUpdated, refreshing, resettingPaper,
      notice, error,
      load, refreshNow, switchBroker, createStrategy, toggleStrategy,
      rotateStrategyKey, resetPaperPortfolio, addInstrument,
      setNotice, setError,
    }}>
      {children}
    </DashboardContext.Provider>
  )
}
