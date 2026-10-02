import type { BrokerStatus, Instrument, Order, Position, Side, Strategy } from './types'

// Support the original deployment variable name as well as the canonical one.
// Both values should include the backend's `/api` prefix.
const API_URL = import.meta.env.VITE_API_URL
  || import.meta.env.VITE_API_BASE_URL
  || 'http://localhost:8000/api'

export class ApiError extends Error {}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('jarvis_token')
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: 'Request failed' }))
    if (response.status === 401 && token) {
      localStorage.removeItem('jarvis_token')
      localStorage.removeItem('jarvis_email')
      window.dispatchEvent(new Event('jarvis:unauthorized'))
    }
    throw new ApiError(payload.detail || 'Request failed')
  }
  return response.json()
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; email: string }>('/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string) =>
    request<{ access_token: string; email: string; strategy_api_key: string }>('/auth/register', {
      method: 'POST', body: JSON.stringify({ email, password }),
    }),
  instruments: (query = '') => request<Instrument[]>(`/instruments?q=${encodeURIComponent(query)}`),
  orders: () => request<Order[]>('/orders'),
  positions: (includeClosed = false) => request<Position[]>(`/positions?include_closed=${includeClosed}`),
  resetPaperPortfolio: () => request<{ message: string; orders_removed: number; positions_removed: number }>('/portfolio/paper/reset', {
    method: 'POST',
  }),
  broker: () => request<BrokerStatus>('/broker'),
  connectBroker: (broker: string) => request<BrokerStatus & { message: string }>('/broker', {
    method: 'PUT', body: JSON.stringify({ broker }),
  }),
  strategies: () => request<Strategy[]>('/strategies'),
  createStrategy: (name: string, description: string) => request<Strategy>('/strategies', {
    method: 'POST', body: JSON.stringify({ name, description }),
  }),
  updateStrategy: (id: number, status: 'ACTIVE' | 'PAUSED') => request<Strategy>(`/strategies/${id}`, {
    method: 'PATCH', body: JSON.stringify({ status }),
  }),
  rotateStrategyKey: () => request<{ strategy_api_key: string; message: string }>('/auth/strategy-key', {
    method: 'POST',
  }),
  placeOrder: (symbol: string, side: Side, quantity: number, confirmLive = false) => request<Order>('/orders', {
    method: 'POST', body: JSON.stringify({ symbol, side, quantity, confirm_live: confirmLive }),
  }),
}
