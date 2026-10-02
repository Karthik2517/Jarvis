import { useEffect, useState } from 'react'
import { Bell, Bookmark, Filter, Play, Plus, RefreshCw, ScanSearch, Trash2 } from 'lucide-react'
import { api } from './api'
import type {
  RankDirection, SavedScanner, ScannerAlert, ScannerAlertEvent, ScannerCatalog,
  ScannerCondition, ScannerField, ScannerOperator, ScannerPage,
} from './types'

const money = new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 2,
})
const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

const fieldLabels: Record<ScannerField, string> = {
  price: 'Price',
  volume: 'Volume',
  avg_volume_20: 'Average Volume 20',
  volume_ratio: 'Volume Ratio',
  sma20: 'SMA 20',
  sma50: 'SMA 50',
  sma200: 'SMA 200',
  rsi14: 'RSI 14',
  prior_52w_high: 'Prior 52W High',
  prior_52w_low: 'Prior 52W Low',
  breakout_percent: 'Breakout %',
  breakdown_percent: 'Breakdown %',
}

type ConditionDraft = ScannerCondition & { id: number; rightType: 'value' | 'field' }

function newCondition(id: number): ConditionDraft {
  return {
    id,
    left: 'price',
    operator: '>',
    rightType: 'field',
    right: { field: 'sma50', multiplier: 1 },
  }
}

function indicator(value: number | null, formatter: (value: number) => string = value => number.format(value)) {
  return value === null ? '—' : formatter(value)
}

export default function ScannerView() {
  const [catalog, setCatalog] = useState<ScannerCatalog | null>(null)
  const [mode, setMode] = useState<'preset' | 'custom'>('preset')
  const [presetKey, setPresetKey] = useState('volume_breakout')
  const [conditions, setConditions] = useState<ConditionDraft[]>([
    newCondition(1),
    { ...newCondition(2), left: 'sma50', right: { field: 'sma200', multiplier: 1 } },
    { ...newCondition(3), left: 'volume', right: { field: 'avg_volume_20', multiplier: 2 } },
    { ...newCondition(4), left: 'rsi14', rightType: 'value', right: { value: 55 } },
  ])
  const [rankField, setRankField] = useState<ScannerField>('price')
  const [rankDirection, setRankDirection] = useState<RankDirection>('desc')
  const [result, setResult] = useState<ScannerPage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [nextId, setNextId] = useState(5)
  const [savedScanners, setSavedScanners] = useState<SavedScanner[]>([])
  const [alerts, setAlerts] = useState<ScannerAlert[]>([])
  const [alertEvents, setAlertEvents] = useState<ScannerAlertEvent[]>([])
  const [saveName, setSaveName] = useState('')
  const [alertName, setAlertName] = useState('')
  const [alertScannerId, setAlertScannerId] = useState(0)
  const [minimumMatches, setMinimumMatches] = useState(1)
  const [managementBusy, setManagementBusy] = useState<number | 'save' | 'alert' | null>(null)
  const [managementMessage, setManagementMessage] = useState('')

  useEffect(() => {
    api.scanners()
      .then(data => {
        setCatalog(data)
        if (data.presets.length && !data.presets.some(item => item.key === presetKey)) {
          setPresetKey(data.presets[0].key)
        }
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load scanners'))
    Promise.all([api.savedScanners(), api.scannerAlerts(), api.scannerAlertEvents()])
      .then(([saved, scannerAlerts, events]) => {
        setSavedScanners(saved); setAlerts(scannerAlerts); setAlertEvents(events)
        if (saved.length) setAlertScannerId(saved[0].id)
      })
      .catch(err => setError(err instanceof Error ? err.message : 'Could not load scanner workspace'))
  }, [])

  function requestConditions() {
    return conditions.map(({ id: _id, rightType: _rightType, ...item }) => item)
  }

  async function saveCurrentScanner() {
    if (!saveName.trim()) { setError('Enter a name before saving the scanner'); return }
    setManagementBusy('save'); setError(''); setManagementMessage('')
    try {
      const saved = await api.saveScanner({
        name: saveName.trim(),
        ...(mode === 'preset' ? { preset_key: presetKey } : { conditions: requestConditions() }),
        rank_field: rankField,
        rank_direction: rankDirection,
      })
      setSavedScanners(current => [saved, ...current])
      setAlertScannerId(saved.id); setSaveName('')
      setManagementMessage(`Saved “${saved.name}”`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save scanner')
    } finally { setManagementBusy(null) }
  }

  function loadSavedScanner(saved: SavedScanner) {
    setResult(null); setError(''); setManagementMessage(`Loaded “${saved.name}”`)
    setRankField(saved.rank_field); setRankDirection(saved.rank_direction)
    if (saved.preset_key) {
      setMode('preset'); setPresetKey(saved.preset_key)
      return
    }
    setMode('custom')
    setConditions(saved.conditions.map((condition, index) => ({
      ...condition,
      id: index + 1,
      rightType: condition.right.field ? 'field' : 'value',
    })))
    setNextId(saved.conditions.length + 1)
  }

  async function deleteSavedScanner(id: number) {
    setManagementBusy(id); setError('')
    try {
      await api.deleteSavedScanner(id)
      const remaining = savedScanners.filter(item => item.id !== id)
      setSavedScanners(remaining)
      if (alertScannerId === id) setAlertScannerId(remaining[0]?.id || 0)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not delete scanner') }
    finally { setManagementBusy(null) }
  }

  async function createAlert() {
    if (!alertScannerId || !alertName.trim()) { setError('Choose a saved scanner and enter an alert name'); return }
    setManagementBusy('alert'); setError(''); setManagementMessage('')
    try {
      const created = await api.createScannerAlert(alertScannerId, alertName.trim(), minimumMatches)
      setAlerts(current => [created, ...current]); setAlertName('')
      setManagementMessage(`Alert “${created.name}” created`)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not create alert') }
    finally { setManagementBusy(null) }
  }

  async function toggleAlert(alert: ScannerAlert) {
    setManagementBusy(alert.id); setError('')
    try {
      const updated = await api.updateScannerAlert(alert.id, { enabled: !alert.enabled })
      setAlerts(current => current.map(item => item.id === alert.id ? updated : item))
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not update alert') }
    finally { setManagementBusy(null) }
  }

  async function evaluateAlert(alert: ScannerAlert) {
    setManagementBusy(alert.id); setError(''); setManagementMessage('')
    try {
      const evaluation = await api.evaluateScannerAlert(alert.id)
      const [updatedAlerts, events] = await Promise.all([api.scannerAlerts(), api.scannerAlertEvents()])
      setAlerts(updatedAlerts); setAlertEvents(events)
      setManagementMessage(evaluation.triggered
        ? `${alert.name} triggered with ${evaluation.match_count} matches`
        : `${alert.name} checked: ${evaluation.match_count} matches`)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not evaluate alert') }
    finally { setManagementBusy(null) }
  }

  async function deleteAlert(id: number) {
    setManagementBusy(id); setError('')
    try {
      await api.deleteScannerAlert(id)
      setAlerts(current => current.filter(item => item.id !== id))
      setAlertEvents(current => current.filter(item => item.alert_id !== id))
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not delete alert') }
    finally { setManagementBusy(null) }
  }

  function updateCondition(id: number, update: Partial<ConditionDraft>) {
    setConditions(current => current.map(item => item.id === id ? { ...item, ...update } : item))
    setResult(null)
  }

  function changeRightType(item: ConditionDraft, rightType: 'value' | 'field') {
    updateCondition(item.id, {
      rightType,
      right: rightType === 'value' ? { value: 0 } : { field: 'sma50', multiplier: 1 },
    })
  }

  function addCondition() {
    if (conditions.length >= 10) return
    setConditions(current => [...current, newCondition(nextId)])
    setNextId(value => value + 1)
    setResult(null)
  }

  function removeCondition(id: number) {
    if (conditions.length === 1) return
    setConditions(current => current.filter(item => item.id !== id))
    setResult(null)
  }

  async function run(page = 1, refresh = page === 1) {
    if (mode === 'custom' && conditions.length === 0) return
    setLoading(true); setError('')
    try {
      const response = await api.runScanner({
        ...(mode === 'preset'
          ? { preset_key: presetKey }
          : {
              conditions: requestConditions(),
              rank_field: rankField,
              rank_direction: rankDirection,
            }),
        page,
        page_size: 25,
        refresh,
      })
      setResult(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scanner run failed')
    } finally {
      setLoading(false)
    }
  }

  const fields = catalog?.fields || (Object.keys(fieldLabels) as ScannerField[])
  const operators = catalog?.operators || (['>', '>=', '<', '<=', '=='] as ScannerOperator[])

  return <div className="scanner-view">
    <section className="scanner-mode-bar">
      <div className="scanner-tabs">
        <button className={mode === 'preset' ? 'active' : ''} onClick={() => { setMode('preset'); setResult(null) }}>Preset scanners</button>
        <button className={mode === 'custom' ? 'active' : ''} onClick={() => { setMode('custom'); setResult(null) }}>Custom conditions</button>
      </div>
      <span><ScanSearch size={15}/> NIFTY 50 · Daily candles</span>
    </section>

    {mode === 'preset' ? <section className="scanner-presets">
      {(catalog?.presets || []).map(preset => <button
        key={preset.key}
        className={presetKey === preset.key ? 'active' : ''}
        onClick={() => { setPresetKey(preset.key); setResult(null) }}
      >
        <span className="scanner-preset-icon"><ScanSearch size={17}/></span>
        <strong>{preset.name}</strong>
        <small>{preset.description}</small>
        <em>{preset.minimum_history} sessions</em>
      </button>)}
    </section> : <section className="card condition-builder">
      <div className="card-heading">
        <div><span className="kicker">FILTER BUILDER</span><h2>All conditions must match</h2></div>
        <button className="secondary-button" onClick={addCondition} disabled={conditions.length >= 10}><Plus size={14}/> Add condition</button>
      </div>
      <div className="condition-list">
        {conditions.map((item, index) => <div className="condition-row" key={item.id}>
          <span className="condition-join">{index === 0 ? 'WHERE' : 'AND'}</span>
          <select value={item.left} onChange={event => updateCondition(item.id, { left: event.target.value as ScannerField })}>
            {fields.map(field => <option key={field} value={field}>{fieldLabels[field]}</option>)}
          </select>
          <select className="operator-select" value={item.operator} onChange={event => updateCondition(item.id, { operator: event.target.value as ScannerOperator })}>
            {operators.map(operator => <option key={operator}>{operator}</option>)}
          </select>
          <select value={item.rightType} onChange={event => changeRightType(item, event.target.value as 'value' | 'field')}>
            <option value="field">Indicator</option><option value="value">Number</option>
          </select>
          {item.rightType === 'field' ? <>
            <input aria-label="Multiplier" type="number" step="0.1" value={item.right.multiplier ?? 1} onChange={event => updateCondition(item.id, { right: { ...item.right, multiplier: Number(event.target.value) } })}/>
            <span className="multiply">×</span>
            <select value={item.right.field} onChange={event => updateCondition(item.id, { right: { ...item.right, field: event.target.value as ScannerField } })}>
              {fields.map(field => <option key={field} value={field}>{fieldLabels[field]}</option>)}
            </select>
          </> : <input aria-label="Comparison value" type="number" step="0.1" value={item.right.value ?? 0} onChange={event => updateCondition(item.id, { right: { value: Number(event.target.value) } })}/>}
          <button className="remove-condition" title="Remove condition" disabled={conditions.length === 1} onClick={() => removeCondition(item.id)}><Trash2 size={15}/></button>
        </div>)}
      </div>
      <div className="rank-controls">
        <label>Rank results by<select value={rankField} onChange={event => setRankField(event.target.value as ScannerField)}>{fields.map(field => <option key={field} value={field}>{fieldLabels[field]}</option>)}</select></label>
        <label>Direction<select value={rankDirection} onChange={event => setRankDirection(event.target.value as RankDirection)}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label>
      </div>
    </section>}

    <section className="scanner-action-row">
      <div className="save-scanner-control">
        <Bookmark size={15}/>
        <input value={saveName} maxLength={80} placeholder="Name this scanner" onChange={event => setSaveName(event.target.value)}/>
        <button className="secondary-button" onClick={saveCurrentScanner} disabled={managementBusy === 'save' || !catalog}>Save</button>
      </div>
      <div className="scanner-run-row">
        <div><Filter size={15}/><span>Read-only market scan. No orders are created.</span></div>
        <button className="primary scanner-run" onClick={() => run(1, true)} disabled={loading || !catalog}>
          {loading ? <><RefreshCw className="search-spinner" size={16}/> Scanning NSE…</> : <><ScanSearch size={16}/> Run scanner</>}
        </button>
      </div>
    </section>

    {error && <div className="alert error">{error}</div>}
    {managementMessage && <div className="alert success">{managementMessage}</div>}
    {result && <>
      <section className="scanner-summary">
        <div><span>Matches</span><strong>{result.total_matches}</strong></div>
        <div><span>Evaluated</span><strong>{result.evaluated}</strong></div>
        <div><span>Universe</span><strong>{result.total_instruments}</strong></div>
        <div><span>Skipped</span><strong>{result.skipped_count}</strong></div>
      </section>
      <section className="card scanner-results">
        <div className="card-heading"><div><span className="kicker">SCAN RESULTS</span><h2>Matching NIFTY 50 stocks</h2></div><small>Page {result.page} of {result.total_pages}</small></div>
        {result.items.length === 0 ? <div className="scanner-empty"><ScanSearch size={28}/><strong>No stocks matched</strong><span>Adjust the conditions and run the scanner again.</span></div> : <div className="table-wrap"><table><thead><tr><th>Rank</th><th>Stock</th><th>Price</th><th>Volume</th><th>Vol. ratio</th><th>SMA 20</th><th>SMA 50</th><th>SMA 200</th><th>RSI 14</th><th>Rank value</th><th>As of</th></tr></thead><tbody>
          {result.items.map(item => <tr key={item.instrument_key}>
            <td><span className="scan-rank">#{item.rank}</span></td>
            <td><strong>{item.symbol}</strong><small>{item.name}</small></td>
            <td>{money.format(item.indicators.price)}</td>
            <td>{number.format(item.indicators.volume)}</td>
            <td>{indicator(item.indicators.volume_ratio, value => `${value.toFixed(2)}×`)}</td>
            <td>{indicator(item.indicators.sma20, money.format)}</td>
            <td>{indicator(item.indicators.sma50, money.format)}</td>
            <td>{indicator(item.indicators.sma200, money.format)}</td>
            <td>{indicator(item.indicators.rsi14)}</td>
            <td className="gain">{number.format(item.rank_value)}</td>
            <td>{item.data_as_of}</td>
          </tr>)}
        </tbody></table></div>}
        {result.total_pages > 1 && <div className="pagination">
          <button disabled={!result.has_previous || loading} onClick={() => run(result.page - 1, false)}>Previous</button>
          <span>Page {result.page} of {result.total_pages}</span>
          <button disabled={!result.has_next || loading} onClick={() => run(result.page + 1, false)}>Next</button>
        </div>}
      </section>
    </>}

    <section className="scanner-management-grid">
      <div className="card scanner-management-card alert-management-card">
        <div className="card-heading"><div><span className="kicker">SAVED SCANNERS</span><h2>Reusable scanner setups</h2></div><Bookmark size={18}/></div>
        {savedScanners.length === 0 ? <div className="scanner-management-empty">Save the current preset or custom conditions to reuse them.</div> : <div className="saved-scanner-list">
          {savedScanners.map(saved => <div className="saved-scanner-row" key={saved.id}>
            <button className="saved-scanner-main" onClick={() => loadSavedScanner(saved)}>
              <strong>{saved.name}</strong><span>{saved.preset_key ? 'Preset' : `${saved.conditions.length} custom conditions`}</span>
            </button>
            <button className="icon-action danger" title="Delete saved scanner" disabled={managementBusy === saved.id} onClick={() => deleteSavedScanner(saved.id)}><Trash2 size={14}/></button>
          </div>)}
        </div>}
      </div>

      <div className="card scanner-management-card">
        <div className="card-heading"><div><span className="kicker">IN-APP ALERTS</span><h2>Notify on scanner matches</h2></div><Bell size={18}/></div>
        <div className="alert-create-row">
          <select value={alertScannerId} onChange={event => setAlertScannerId(Number(event.target.value))} disabled={!savedScanners.length}>
            {!savedScanners.length && <option value={0}>Save a scanner first</option>}
            {savedScanners.map(saved => <option key={saved.id} value={saved.id}>{saved.name}</option>)}
          </select>
          <input value={alertName} maxLength={80} placeholder="Alert name" onChange={event => setAlertName(event.target.value)}/>
          <label>Min.<input type="number" min={1} max={10000} value={minimumMatches} onChange={event => setMinimumMatches(Math.max(1, Number(event.target.value)))}/></label>
          <button className="secondary-button" onClick={createAlert} disabled={!savedScanners.length || managementBusy === 'alert'}><Plus size={14}/> Create</button>
        </div>
        {alerts.length === 0 ? <div className="scanner-management-empty">Alerts appear here after you create one.</div> : <div className="scanner-alert-list">
          {alerts.map(alert => <div className="scanner-alert-row" key={alert.id}>
            <button className={`alert-toggle ${alert.enabled ? 'enabled' : ''}`} onClick={() => toggleAlert(alert)} disabled={managementBusy === alert.id} aria-label={`${alert.enabled ? 'Disable' : 'Enable'} ${alert.name}`}><span/></button>
            <div><strong>{alert.name}</strong><span>{alert.saved_scanner_name} · triggers at {alert.minimum_matches}+ matches</span></div>
            <button className="icon-action" title="Check alert now" disabled={!alert.enabled || managementBusy === alert.id} onClick={() => evaluateAlert(alert)}><Play size={14}/></button>
            <button className="icon-action danger" title="Delete alert" disabled={managementBusy === alert.id} onClick={() => deleteAlert(alert.id)}><Trash2 size={14}/></button>
          </div>)}
        </div>}
      </div>
    </section>

    {alertEvents.length > 0 && <section className="card scanner-events">
      <div className="card-heading"><div><span className="kicker">RECENT ALERTS</span><h2>Triggered scanner alerts</h2></div><small>Latest 100 events</small></div>
      <div className="scanner-event-list">{alertEvents.map(event => <div className={event.is_read ? 'read' : ''} key={event.id}>
        <Bell size={15}/><p><strong>{event.alert_name}</strong><span>{event.match_count} matches · {event.symbols.slice(0, 6).join(', ')}{event.symbols.length > 6 ? '…' : ''}</span></p><time>{event.data_as_of || 'Latest completed session'}</time>
      </div>)}</div>
    </section>}
  </div>
}
