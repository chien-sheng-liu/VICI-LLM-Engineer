import React from 'react'

type KPI = Record<string, any>

type Props = {
  sections: any | null
  reportContent: string
}

const toNumber = (value: any) => {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    // allow digits, plus, minus, and decimal dot
    const cleaned = value.replace(/[^0-9+.-]/g, '')
    const parsed = Number(cleaned)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

const formatNumber = (value: any, digits = 2) => {
  const num = toNumber(value)
  if (num === null) return typeof value === 'undefined' ? '—' : String(value)
  try {
    return Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(num)
  } catch {
    return num.toString()
  }
}

const formatMoney = (value: any, currency?: string) => {
  const num = toNumber(value)
  if (num === null) return typeof value === 'undefined' ? '—' : String(value)
  if (currency) {
    try {
      return Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(num)
    } catch (_e) {
      return formatNumber(num, 2)
    }
  }
  return formatNumber(num, 2)
}

const formatCompact = (value: any) => {
  const num = toNumber(value)
  if (num === null) return typeof value === 'undefined' ? '—' : String(value)
  try {
    return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(num)
  } catch {
    const abs = Math.abs(num)
    const units = [
      { unit: 1e12, suffix: 'T' },
      { unit: 1e9, suffix: 'B' },
      { unit: 1e6, suffix: 'M' },
      { unit: 1e3, suffix: 'K' },
    ]
    for (const { unit, suffix } of units) {
      if (abs >= unit) {
        return `${(num / unit).toFixed(abs / unit >= 10 ? 0 : 2)}${suffix}`
      }
    }
    return formatNumber(num)
  }
}

export const ArtifactViewer: React.FC<Props> = ({ sections, reportContent }) => {
  const data = sections?.report_sections || sections || null
  if (!data) {
    return <div className="md">{reportContent || 'No report yet.'}</div>
  }

  const kpis: KPI = data.kpis || {}
  const fin = data.fin_analysis || {}
  const finBasic = data.finance_basic || {}
  const watch: any[] = data.watch_items || []
  const traderSignals = data.trader_signals || null
  const table = Array.isArray(data.table) ? data.table : []

  const ticker = (data.ticker || data.symbol || '').toUpperCase() || '尚未取得'
  const company = data.company_name || kpis.company_name || '尚未取得'
  const source = data.source || '—'
  const summaryText = (data.summary && String(data.summary).trim()) || ''
  const traderNotes = (data.trader_insights && String(data.trader_insights).trim())
    || (Array.isArray(data.trader_insights_list) ? data.trader_insights_list.join(' / ') : '')
  const heroNotes = traderNotes || fin.thesis || summaryText || '等待代理人完成分析。'

  const composite: number | undefined = typeof traderSignals?.composite_score === 'number' ? traderSignals.composite_score : undefined
  const stance = (() => {
    if (composite && composite >= 4) return { label: 'Bullish Lean', tone: 'long' }
    if (composite && composite <= 2.5) return { label: 'Defensive', tone: 'short' }
    return { label: 'Neutral Range', tone: 'flat' }
  })()

  const metrics = [
    { label: 'Confidence', value: typeof fin.confidence === 'number' ? `${fin.confidence}/5` : '—' },
    { label: 'Timeframe', value: fin.timeframe || '—' },
    { label: 'Exp. Move', value: typeof fin.expected_move_pct === 'number' ? `${fin.expected_move_pct}%` : '—' },
    { label: 'Composite', value: composite ? `${composite}/5` : '—' },
  ]

  const flowStats = traderSignals ? [
    { label: 'Trend', value: traderSignals.trend_score },
    { label: 'Momentum', value: traderSignals.momentum_score },
    { label: 'Volume', value: traderSignals.volume_score },
    { label: 'Volatility', value: traderSignals.volatility_pct ? `${formatNumber(traderSignals.volatility_pct)}%` : '—' },
  ] : []

  const keyLevels: string[] = []
  if (typeof kpis.prev_close !== 'undefined') keyLevels.push(`Pivot ${formatMoney(kpis.prev_close, kpis.currency)}`)
  if (typeof kpis.day_low !== 'undefined') keyLevels.push(`Day Low ${formatMoney(kpis.day_low, kpis.currency)}`)
  if (typeof kpis.day_high !== 'undefined') keyLevels.push(`Day High ${formatMoney(kpis.day_high, kpis.currency)}`)
  if (typeof traderSignals?.bb_lower !== 'undefined') keyLevels.push(`BB- ${formatNumber(traderSignals.bb_lower)}`)
  if (typeof traderSignals?.bb_upper !== 'undefined') keyLevels.push(`BB+ ${formatNumber(traderSignals.bb_upper)}`)
  if (typeof kpis.target_mean_price !== 'undefined') keyLevels.push(`Street PT ${formatMoney(kpis.target_mean_price, kpis.currency)}`)

  const kpiCards = [
    { label: 'Price', value: formatMoney(kpis.price ?? data.price, kpis.currency) },
    { label: 'Change', value: kpis.change_percent ? `${formatNumber(kpis.change_percent)}%` : (kpis.change ? formatNumber(kpis.change) : '—') },
    { label: 'Volume', value: kpis.volume ? formatNumber(kpis.volume, 0) : '—' },
    { label: 'Market Cap', value: kpis.market_cap ? formatCompact(kpis.market_cap) : (finBasic.market_cap ? formatCompact(finBasic.market_cap) : '—') },
    { label: 'Fwd P/E', value: formatNumber(kpis.pe_fwd || finBasic.pe_fwd) },
    { label: 'Yield', value: kpis.dividend_yield_pct ? `${formatNumber(kpis.dividend_yield_pct)}%` : '—' },
  ]

  const basics = [
    { label: 'Gross Margin', value: finBasic.gross_margin_pct ? `${formatNumber(finBasic.gross_margin_pct)}%` : '—' },
    { label: 'Op Margin', value: finBasic.operating_margin_pct ? `${formatNumber(finBasic.operating_margin_pct)}%` : '—' },
    { label: 'Profit Margin', value: finBasic.profit_margin_pct ? `${formatNumber(finBasic.profit_margin_pct)}%` : '—' },
    { label: 'ROE', value: finBasic.roe_pct ? `${formatNumber(finBasic.roe_pct)}%` : '—' },
    { label: 'Revenue Growth', value: finBasic.revenue_growth_pct ? `${formatNumber(finBasic.revenue_growth_pct)}%` : '—' },
    { label: 'Earnings Growth', value: finBasic.earnings_growth_pct ? `${formatNumber(finBasic.earnings_growth_pct)}%` : '—' },
  ]

  return (
    <div className="report-surface">
      <section className={`report-hero-block ${stance.tone}`}>
        <div className="report-headline">
          <div>
            <div className="ticker-chip">{ticker}</div>
            <h2>{company}</h2>
            <p className="muted small">Source: {source}</p>
          </div>
          <div className="hero-metric-grid">
            {metrics.map((item) => (
              <div key={item.label} className="mini-callout">
                <div className="label">{item.label}</div>
                <div className="value">{item.value}</div>
              </div>
            ))}
          </div>
        </div>
        <p className="hero-notes">{heroNotes}</p>
      </section>

      <section className="report-panel">
        <div className="panel-title">Trade Setup</div>
        <div className="trade-grid">
          <div>
            <div className="label">Thesis</div>
            <p>{fin.thesis || summaryText || '代理人尚未提供論點。'}</p>
          </div>
          <div>
            <div className="label">Trader Notes</div>
            <p>{traderNotes || '尚無交易員備註。'}</p>
          </div>
        </div>
        <div className="list-row">
          <div>
            <div className="label">Drivers</div>
            <ul>
              {(Array.isArray(fin.drivers) && fin.drivers.length > 0 ? fin.drivers : ['尚未辨識主要驅動']).map((item: string, idx: number) => (
                <li key={`driver-${idx}`}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <div className="label">Risks</div>
            <ul>
              {(Array.isArray(fin.risks) && fin.risks.length > 0 ? fin.risks : ['尚未辨識主要風險']).map((item: string, idx: number) => (
                <li key={`risk-${idx}`}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <div className="label">Strategy</div>
            <ul>
              {(Array.isArray(fin.positioning) && fin.positioning.length > 0 ? fin.positioning : ['尚未提供策略建議']).map((item: string, idx: number) => (
                <li key={`pos-${idx}`}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="report-panel">
        <div className="panel-title">Market Structure</div>
        <div className="kpi-grid">
          {kpiCards.map((card) => (
            <div key={card.label} className="kpi">
              <div className="k">{card.label}</div>
              <div className="v">{card.value || '—'}</div>
            </div>
          ))}
        </div>
      </section>

      {flowStats.length > 0 && (
        <section className="report-panel">
          <div className="panel-title">Flow Snapshot</div>
          <div className="signal-grid">
            {flowStats.map((sig) => (
              <div key={sig.label} className="signal-card">
                <div className="label">{sig.label}</div>
                <div className="value">{sig.value ?? '—'}</div>
              </div>
            ))}
          </div>
          {keyLevels.length > 0 && (
            <div className="levels-row">
              {keyLevels.map((lvl, idx) => (
                <span className="pill meta" key={idx}>{lvl}</span>
              ))}
            </div>
          )}
        </section>
      )}

      {basics.some((b) => b.value !== '—') && (
        <section className="report-panel">
          <div className="panel-title">Financial Snapshot</div>
          <div className="signal-grid">
            {basics.map((item) => (
              <div key={item.label} className="signal-card compact">
                <div className="label">{item.label}</div>
                <div className="value">{item.value}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {watch.length > 0 && (
        <section className="report-panel">
          <div className="panel-title">Radar / Triggers</div>
          <ul className="watch-list">
            {watch.map((w:any, i:number)=>(
              <li key={i}>
                <div className="watch-head">
                  <strong>{w.metric}</strong>
                  <span className="pill">P{w.priority || '-'}</span>
                </div>
                <div className="muted">{w.rationale}</div>
                <div className="muted">Check: {w.suggested_check}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {table.length > 0 && (
        <section className="report-panel">
          <div className="panel-title">Auto Table Capture</div>
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  {Object.keys(table[0]).map((k) => (<th key={k}>{k}</th>))}
                </tr>
              </thead>
              <tbody>
                {table.slice(0,4).map((row, idx) => (
                  <tr key={idx}>
                    {Object.keys(table[0]).map((k) => (<td key={`${idx}-${k}`}>{row[k]}</td>))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
