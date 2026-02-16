import React from 'react'

type KPI = Record<string, any>
type NewsItem = { title: string; url: string; time?: string; source?: string }

type Props = {
  sections: any | null
  reportContent: string
  newsItems: NewsItem[]
}

export const ArtifactViewer: React.FC<Props> = ({ sections, reportContent, newsItems }) => {
  if (!sections) {
    return <div className="md">{reportContent || 'No report yet.'}</div>
  }

  const kpis: KPI = sections.kpis || {}
  const events: any[] = sections.events_struct || []
  const watch: any[] = sections.watch_items || []
  const fin = sections.fin_analysis || {}
  const trend = (() => {
    if (!fin) return null
    const pct = typeof fin.expected_move_pct === 'number' ? fin.expected_move_pct : null
    const tf = fin.timeframe || ''
    if (pct === null) return null
    const arrow = pct > 0 ? '↗︎' : (pct < 0 ? '↘︎' : '→')
    const label = `${arrow} ${Math.abs(pct)}%${tf ? `｜${tf}` : ''}`
    return label
  })()
  const kpiArrow = (d?: string) => d === '上' ? '↗︎' : (d === '下' ? '↘︎' : '→')
  const finBasic = sections.finance_basic || {}
  const fmt = (v: any) => (v === null || typeof v === 'undefined' ? '-' : v)
  const compact = (v: any) => {
    if (v === null || typeof v === 'undefined') return '-'
    if (typeof v !== 'number') return String(v)
    try { return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(v) } catch { return v.toLocaleString() }
  }
  const clsPn = (n?: number) => (typeof n === 'number' ? (n > 0 ? 'pos' : (n < 0 ? 'neg' : '')) : '')
  const traderSignals = sections.trader_signals || null
  const currency: string | undefined = (kpis && kpis.currency ? String(kpis.currency) : undefined)
  const fmtMoney = (v: any) => {
    if (v === null || typeof v === 'undefined') return '-'
    if (typeof v !== 'number') return String(v)
    if (currency && currency.length === 3) {
      try { return Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 2 }).format(v) } catch {
        return v.toLocaleString()
      }
    }
    return v.toLocaleString()
  }
  const series: number[] = Array.isArray((sections as any)?.price_series) ? (sections as any).price_series : []
  const sparkPath = (() => {
    if (!series || series.length < 2) return ''
    const w = 100, h = 28
    const min = Math.min(...series), max = Math.max(...series)
    const span = max - min || 1
    const step = w / (series.length - 1)
    const points = series.map((v, i) => {
      const x = i * step
      const y = h - ((v - min) / span) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    return `M ${points[0]} L ${points.slice(1).join(' ')}`
  })()
  const composite: number | undefined = (typeof (sections as any)?.trader_signals?.composite_score === 'number'
    ? (sections as any).trader_signals.composite_score : undefined)
  const scoreClass = composite ? (composite >= 4 ? 'score-good' : (composite >= 3 ? 'score-mid' : 'score-poor')) : 'score-mid'

  return (
    <div className="report-layout">
      {sections.trader_insights && (
        <div className="report-hero card">
          <div className="section-title">交易概覽</div>
          <div className="overview-row">
            <div className={`score-badge ${scoreClass}`}>{composite ? `${composite}/5` : '—'}</div>
            <div className="ovl-cols">
              <div className="kv"><div className="k">期間</div><div>{fin.timeframe || '-'}</div></div>
              <div className="kv"><div className="k">預期波動</div><div>{typeof fin.expected_move_pct === 'number' ? `${fin.expected_move_pct}%` : '-'}</div></div>
              <div className="kv"><div className="k">信心</div><div>{typeof fin.confidence === 'number' ? `${fin.confidence}/5` : '-'}</div></div>
            </div>
          </div>
          <div className="md" style={{ marginTop: 8 }}>{sections.trader_insights}</div>
        </div>
      )}
      <div className="report-hero card">
        <div className="section-title">財務分析（量化視角）</div>
        <div className="md">{fin.thesis || '近期新聞與KPI顯示需關注需求、毛利與法人預期變化。'}</div>
        <div style={{ display: 'grid', gap: 6, marginTop: 8 }}>
          {Array.isArray(fin.drivers) && fin.drivers.length > 0 && (<div className="kv"><div className="k">驅動</div><div>- {fin.drivers.join('\n- ')}</div></div>)}
          {Array.isArray(fin.risks) && fin.risks.length > 0 && (<div className="kv"><div className="k">風險</div><div>- {fin.risks.join('\n- ')}</div></div>)}
          {Array.isArray(fin.positioning) && fin.positioning.length > 0 && (<div className="kv"><div className="k">部位/策略</div><div>- {fin.positioning.join('\n- ')}</div></div>)}
          {Array.isArray(fin.metrics_to_watch) && fin.metrics_to_watch.length > 0 && (<div className="kv"><div className="k">觀測</div><div>- {fin.metrics_to_watch.join('\n- ')}</div></div>)}
          <div className="kv"><div className="k">區間/波動/信心</div><div>{fin.timeframe || '-'} ｜ {typeof fin.expected_move_pct==='number' ? `${fin.expected_move_pct}%` : '-'} ｜ {typeof fin.confidence==='number' ? `${fin.confidence}/5` : '-'}</div></div>
        </div>
      </div>

      {kpis && Object.keys(kpis).length > 0 && (
        <div className="report-card">
          <div className="section-title">重點 KPI</div>
          <div className="kpi-grid">
            {'price' in kpis && (
              <div className="kpi"><div className="k">現價</div><div className={`v ${clsPn(kpis.change)}`}>{fmtMoney(kpis.price)}</div>{sparkPath && (<svg width="100" height="28" viewBox="0 0 100 28"><path d={sparkPath} fill="none" stroke={(series && series.length>1 && series[series.length-1] >= series[0]) ? 'var(--success)' : 'var(--danger)'} strokeWidth="1.5" opacity="0.9"/></svg>)}</div>
            )}
            {'change' in kpis && (
              <div className="kpi"><div className="k">漲跌</div><div className={`v ${clsPn(kpis.change)}`}>{kpis.change} ({typeof kpis.change_percent==='number' ? (kpis.change_percent.toFixed(2)+'%') : kpis.change_percent})</div></div>
            )}
            {'open' in kpis && (
              <div className="kpi"><div className="k">開盤</div><div className="v">{fmtMoney(kpis.open)}</div></div>
            )}
            {'prev_close' in kpis && (
              <div className="kpi"><div className="k">收盤</div><div className="v">{fmtMoney(kpis.prev_close)}</div></div>
            )}
            {'day_high' in kpis && (
              <div className="kpi"><div className="k">日高</div><div className="v">{fmtMoney(kpis.day_high)}</div></div>
            )}
            {'day_low' in kpis && (
              <div className="kpi"><div className="k">日低</div><div className="v">{fmtMoney(kpis.day_low)}</div></div>
            )}
            {'volume' in kpis && (
              <div className="kpi"><div className="k">量</div><div className="v" style={{ fontSize: 12 }}>{compact(kpis.volume)}{kpis.avg_volume_3m ? `（3M ${compact(kpis.avg_volume_3m)}）` : ''}</div></div>
            )}
            {'target_mean_price' in kpis && (
              <div className="kpi"><div className="k">法人平均目標價</div><div className="v">{kpis.target_mean_price}</div></div>
            )}
            {'gross_margin_pct' in kpis && (
              <div className="kpi"><div className="k">毛利率</div><div className="v">{(kpis.gross_margin_pct?.toFixed ? kpis.gross_margin_pct.toFixed(1) : kpis.gross_margin_pct)}%</div></div>
            )}
            {'latest_eps' in kpis && (
              <div className="kpi"><div className="k">最新季度 EPS</div><div className="v">{kpis.latest_eps}</div></div>
            )}
            {'recommendation' in kpis && (
              <div className="kpi"><div className="k">法人建議</div><div className="v">{kpis.recommendation}</div></div>
            )}
            {'market_cap' in kpis && (
              <div className="kpi"><div className="k">市值</div><div className="v">{compact(kpis.market_cap)}</div></div>
            )}
            {'pe_ttm' in kpis && (
              <div className="kpi"><div className="k">本益比(TTM)</div><div className="v">{fmt(kpis.pe_ttm)}</div></div>
            )}
            {'pe_fwd' in kpis && (
              <div className="kpi"><div className="k">預估本益比</div><div className="v">{fmt(kpis.pe_fwd)}</div></div>
            )}
            {'pb' in kpis && (
              <div className="kpi"><div className="k">股價淨值比</div><div className="v">{fmt(kpis.pb)}</div></div>
            )}
            {'dividend_yield_pct' in kpis && (
              <div className="kpi"><div className="k">殖利率</div><div className="v">{fmt(kpis.dividend_yield_pct)}%</div></div>
            )}
          </div>
        </div>
      )}

      {finBasic && Object.keys(finBasic).length > 0 && (
        <div className="report-card">
          <div className="section-title">基本財務</div>
          <ul className="news-list">
            {finBasic.revenue !== undefined && (<li>營收：{compact(finBasic.revenue)}</li>)}
            {finBasic.gross_margin_pct !== undefined && (<li>毛利率：{fmt(finBasic.gross_margin_pct)}%</li>)}
            {finBasic.operating_margin_pct !== undefined && (<li>營業利益率：{fmt(finBasic.operating_margin_pct)}%</li>)}
            {finBasic.profit_margin_pct !== undefined && (<li>淨利率：{fmt(finBasic.profit_margin_pct)}%</li>)}
            {finBasic.roe_pct !== undefined && (<li>ROE：{fmt(finBasic.roe_pct)}%</li>)}
            {finBasic.roa_pct !== undefined && (<li>ROA：{fmt(finBasic.roa_pct)}%</li>)}
            {finBasic.ebitda !== undefined && (<li>EBITDA：{compact(finBasic.ebitda)}</li>)}
            {finBasic.revenue_growth_pct !== undefined && (<li>營收成長：{fmt(finBasic.revenue_growth_pct)}%</li>)}
            {finBasic.earnings_growth_pct !== undefined && (<li>盈餘成長：{fmt(finBasic.earnings_growth_pct)}%</li>)}
          </ul>
        </div>
      )}

      {traderSignals && (
        <div className="report-card">
          <div className="section-title">交易員指標</div>
          <ul className="news-list">
            {traderSignals.price !== undefined && (<li>現價：{fmt(traderSignals.price)}</li>)}
            {traderSignals.sma5 !== undefined && (<li>SMA5：{fmt(traderSignals.sma5)}</li>)}
            {traderSignals.sma20 !== undefined && (<li>SMA20：{fmt(traderSignals.sma20)}</li>)}
            {traderSignals.rsi14 !== undefined && (<li>RSI(14)：{fmt(parseFloat(traderSignals.rsi14?.toFixed?.(2) ?? traderSignals.rsi14))}</li>)}
            {traderSignals.macd !== undefined && (<li>MACD：{fmt(parseFloat(traderSignals.macd?.toFixed?.(3) ?? traderSignals.macd))}（signal：{fmt(parseFloat(traderSignals.macd_signal?.toFixed?.(3) ?? traderSignals.macd_signal))}）</li>)}
            {traderSignals.macd_hist !== undefined && (<li>MACD柱體：{fmt(parseFloat(traderSignals.macd_hist?.toFixed?.(3) ?? traderSignals.macd_hist))}</li>)}
            {traderSignals.volatility_pct !== undefined && (<li>近月波動：{fmt(parseFloat(traderSignals.volatility_pct?.toFixed?.(2) ?? traderSignals.volatility_pct))}%</li>)}
            {traderSignals.volume_ratio !== undefined && (<li>量能比（對3M）：{fmt(parseFloat(traderSignals.volume_ratio?.toFixed?.(2) ?? traderSignals.volume_ratio))}x</li>)}
            {traderSignals.trend_score !== undefined && (<li>趨勢分數：{fmt(traderSignals.trend_score)}</li>)}
            {traderSignals.momentum_score !== undefined && (<li>動能分數：{fmt(traderSignals.momentum_score)}</li>)}
            {traderSignals.volume_score !== undefined && (<li>量能分數：{fmt(traderSignals.volume_score)}</li>)}
            {traderSignals.composite_score !== undefined && (<li>總評分：{fmt(traderSignals.composite_score)}/5</li>)}
            {traderSignals.confidence !== undefined && (<li>信心：{fmt(traderSignals.confidence)}/5</li>)}
          </ul>
        </div>
      )}

      {/* 移除快速摘要：Report 僅保留財務分析與交易相關區塊 */}

      {/* 移除結構化事件 / 指引 / 風險：Report 專注於交易與財務分析指標，不顯示任何新聞衍生內容 */}

      {sections.sentiment && (
        <div className="report-card">
          <div className="section-title">情緒與驚喜</div>
          <div className="md">{sections.sentiment}</div>
        </div>
      )}

      {/* 擷取片段已移除，改以交易員 Insights 呈現 */}

      {/* 移除擷取表格：避免與新聞內容混淆，保留 KPI 卡 */}

      {watch && watch.length > 0 && (
        <div className="report-card">
          <div className="section-title">即時觀測項目</div>
          <ul className="watch-list">
            {watch.map((w:any, i:number)=>(
              <li key={i}>
                <div className="md"><strong>{w.metric}</strong>（優先度 {w.priority || '-'}）</div>
                <div className="muted">{w.rationale}</div>
                <div className="muted">建議檢核：{w.suggested_check}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 移除新聞列表；新聞改到 News 分頁顯示 */}

      {/* 移除來源與時間卡片：避免新聞相關資訊進入 Report */}
    </div>
  )
}
