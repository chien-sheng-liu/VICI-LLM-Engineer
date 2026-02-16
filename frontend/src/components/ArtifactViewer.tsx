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
  const fin = sections.fin_analysis || null
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

  return (
    <div className="report-layout">
      {sections.trader_insights && (
        <div className="report-hero card">
          <div className="section-title">交易員 Insights</div>
          <div className="md">{sections.trader_insights}</div>
        </div>
      )}
      {fin && (
        <div className="report-hero card">
          <div className="section-title">財務分析（量化視角）</div>
          <div className="md">{fin.thesis || '—'}</div>
          <div style={{ display: 'grid', gap: 6, marginTop: 8 }}>
            {Array.isArray(fin.drivers) && fin.drivers.length > 0 && (<div className="kv"><div className="k">驅動</div><div>- {fin.drivers.join('\n- ')}</div></div>)}
            {Array.isArray(fin.risks) && fin.risks.length > 0 && (<div className="kv"><div className="k">風險</div><div>- {fin.risks.join('\n- ')}</div></div>)}
            {Array.isArray(fin.positioning) && fin.positioning.length > 0 && (<div className="kv"><div className="k">部位/策略</div><div>- {fin.positioning.join('\n- ')}</div></div>)}
            {Array.isArray(fin.metrics_to_watch) && fin.metrics_to_watch.length > 0 && (<div className="kv"><div className="k">觀測</div><div>- {fin.metrics_to_watch.join('\n- ')}</div></div>)}
            {(fin.timeframe || fin.expected_move_pct || fin.confidence) && (
              <div className="kv"><div className="k">區間/波動/信心</div><div>{fin.timeframe || '-'} ｜ {typeof fin.expected_move_pct==='number' ? `${fin.expected_move_pct}%` : '-'} ｜ {typeof fin.confidence==='number' ? `${fin.confidence}/5` : '-'}</div></div>
            )}
          </div>
        </div>
      )}

      {kpis && Object.keys(kpis).length > 0 && (
        <div className="report-card">
          <div className="section-title">重點 KPI</div>
          <div className="kpi-grid">
            {'price' in kpis && (
              <div className="kpi"><div className="k">最新股價</div><div className="v">{kpis.price} {kpis.currency || ''}</div></div>
            )}
            {'change' in kpis && (
              <div className="kpi"><div className="k">漲跌</div><div className="v">{kpis.change} ({typeof kpis.change_percent==='number' ? (kpis.change_percent.toFixed(2)+'%') : kpis.change_percent})</div></div>
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
          </div>
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
