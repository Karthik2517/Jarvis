import type {
  BrokerStatus, DashboardSnapshot, Instrument, Order, Position, ScannerCatalog, ScannerPage,
  SavedScanner, ScannerAlert, ScannerAlertEvaluation, ScannerAlertEvent,
  ScannerCondition, ScannerField, ScannerRunRequest, ScannerStreamEvent,
  RankDirection, Side, Strategy,
} from './types'

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

async function streamScanner(
  payload: ScannerRunRequest,
  onEvent: (event: ScannerStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('jarvis_token')
  const response = await fetch(`${API_URL}/scanners/run/stream`, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/x-ndjson',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({ detail: 'Scanner stream failed' }))
    if (response.status === 401 && token) {
      localStorage.removeItem('jarvis_token')
      localStorage.removeItem('jarvis_email')
      window.dispatchEvent(new Event('jarvis:unauthorized'))
    }
    throw new ApiError(errorPayload.detail || 'Scanner stream failed')
  }
  if (!response.body) throw new ApiError('Streaming is not supported by this browser')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false

  // Process one NDJSON line immediately without awaiting.
  // All setState calls inside onEvent from the same synchronous loop
  // iteration are automatically batched by React 18 into one render.
  const processLine = (line: string) => {
    if (!line.trim()) return
    let event: ScannerStreamEvent
    try {
      event = JSON.parse(line) as ScannerStreamEvent
    } catch {
      throw new ApiError('The scanner returned an invalid stream event')
    }
    if (event.type === 'error') throw new ApiError(event.detail)
    if (event.type === 'complete') completed = true
    onEvent(event)
  }

  try {
    while (true) {
      // reader.read() naturally yields to the JS event loop, giving
      // React a render boundary between every TCP chunk.
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      // Process all complete lines in this chunk synchronously so React
      // batches their state updates into a single render per chunk.
      for (const line of lines) processLine(line)
      if (done) break
    }
    // Flush any remaining partial line after EOF.
    if (buffer.trim()) processLine(buffer)
  } finally {
    reader.releaseLock()
  }
  if (!completed) throw new ApiError('The scanner stream ended before completion')
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
  dashboard: () => request<DashboardSnapshot>('/dashboard'),
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
  scanners: () => request<ScannerCatalog>('/scanners'),
  runScanner: (payload: ScannerRunRequest) => request<ScannerPage>('/scanners/run', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  streamScanner,
  scannerResultPage: (scanId: string, page: number, pageSize: number) =>
    request<ScannerPage>(`/scanners/runs/${encodeURIComponent(scanId)}?page=${page}&page_size=${pageSize}`),
  savedScanners: () => request<SavedScanner[]>('/scanners/saved'),
  saveScanner: (payload: {
    name: string; preset_key?: string; conditions?: ScannerCondition[];
    rank_field: ScannerField; rank_direction: RankDirection;
  }) => request<SavedScanner>('/scanners/saved', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  deleteSavedScanner: (id: number) => request<{ message: string }>(`/scanners/saved/${id}`, {
    method: 'DELETE',
  }),
  scannerAlerts: () => request<ScannerAlert[]>('/scanners/alerts'),
  createScannerAlert: (savedScannerId: number, name: string, minimumMatches: number) =>
    request<ScannerAlert>('/scanners/alerts', {
      method: 'POST', body: JSON.stringify({ saved_scanner_id: savedScannerId, name, minimum_matches: minimumMatches }),
    }),
  updateScannerAlert: (id: number, payload: { enabled?: boolean; minimum_matches?: number }) =>
    request<ScannerAlert>(`/scanners/alerts/${id}`, {
      method: 'PATCH', body: JSON.stringify(payload),
    }),
  deleteScannerAlert: (id: number) => request<{ message: string }>(`/scanners/alerts/${id}`, {
    method: 'DELETE',
  }),
  evaluateScannerAlert: (id: number) => request<ScannerAlertEvaluation>(`/scanners/alerts/${id}/evaluate`, {
    method: 'POST',
  }),
  scannerAlertEvents: () => request<ScannerAlertEvent[]>('/scanners/alert-events'),
  markScannerAlertRead: (id: number) => request<{ message: string }>(`/scanners/alert-events/${id}/read`, {
    method: 'PATCH',
  }),
  getProfile: () =>
    request<{ email: string; name: string; created_at: string }>('/auth/me'),
  updateProfile: (payload: { name?: string; current_password?: string; new_password?: string }) =>
    request<{ email: string; name: string; created_at: string }>('/auth/me', {
      method: 'PATCH', body: JSON.stringify(payload),
    }),
}
