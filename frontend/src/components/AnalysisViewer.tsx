import React from 'react'

type Props = {
  sections: any
}

const asArray = (value: any) => (Array.isArray(value) ? value : [])

export const AnalysisViewer: React.FC<Props> = ({ sections }) => {
  const data = sections || {}
  const digest = data.analysis_digest || {}
  const report = (data.analysis_report && String(data.analysis_report).trim()) || ''
  const generated = data.generated_at || ''
  const source = data.source || ''
  const thesis = digest.thesis || ''
  const drivers = asArray(digest.drivers)
  const risks = asArray(digest.risks)
  const positioning = asArray(digest.positioning)
  const traderSummary = digest.trader_summary || ''
  const traderSignals = digest.trader_signals || {}
  const watchFocus = asArray(digest.watch_focus)
  const catalysts = asArray(digest.catalysts)
  const newsSummary = digest.news_summary || ''
  const ragNotes = asArray(digest.rag_notes)

  const signalCards = [
    { label: 'Trend', value: traderSignals.trend },
    { label: 'Momentum', value: traderSignals.momentum },
    { label: 'Volume', value: traderSignals.volume },
    { label: 'Volatility %', value: traderSignals.volatility_pct },
  ].filter((card) => typeof card.value !== 'undefined' && card.value !== null && card.value !== '')

  return (
    <div className="analysis-view">
      <section className="report-panel">
        <div className="panel-title">Executive Analysis</div>
        <div className="muted small" style={{ marginBottom: 10 }}>
          {generated && <span>更新時間：{new Date(generated).toLocaleString()}</span>}
          {source && <span style={{ marginLeft: 12 }}>來源：{source}</span>}
        </div>
        <div className="analysis-text md">
          {report || '代理人尚未產出完整分析報告，請稍後查看或重新執行一次。'}
        </div>
      </section>

      {(thesis || drivers.length || risks.length || positioning.length) && (
        <section className="report-panel">
          <div className="panel-title">Researcher Highlights</div>
          {thesis && <p><strong>Thesis：</strong>{thesis}</p>}
          {drivers.length > 0 && (
            <div>
              <div className="label">Drivers</div>
              <ul className="analysis-list">
                {drivers.map((item: string, idx: number) => (
                  <li key={`driver-${idx}`}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {risks.length > 0 && (
            <div>
              <div className="label">Risks</div>
              <ul className="analysis-list">
                {risks.map((item: string, idx: number) => (
                  <li key={`risk-${idx}`}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {positioning.length > 0 && (
            <div>
              <div className="label">Positioning</div>
              <ul className="analysis-list">
                {positioning.map((item: string, idx: number) => (
                  <li key={`pos-${idx}`}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {(traderSummary || signalCards.length > 0) && (
        <section className="report-panel">
          <div className="panel-title">Trader Desk</div>
          {traderSummary && <p>{traderSummary}</p>}
          {signalCards.length > 0 && (
            <div className="signal-grid" style={{ marginTop: 10 }}>
              {signalCards.map((card) => (
                <div key={card.label} className="signal-card compact">
                  <div className="label">{card.label}</div>
                  <div className="value">{card.value}</div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {(newsSummary || catalysts.length > 0) && (
        <section className="report-panel">
          <div className="panel-title">Catalyst Radar</div>
          {newsSummary && <p className="muted">{newsSummary}</p>}
          {catalysts.length > 0 && (
            <ul className="analysis-list">
              {catalysts.map((item: string, idx: number) => (
                <li key={`catalyst-${idx}`}>{item}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {watchFocus.length > 0 && (
        <section className="report-panel">
          <div className="panel-title">Watch Focus</div>
          <ul className="analysis-list">
            {watchFocus.map((item: any, idx: number) => (
              <li key={`watch-${idx}`}>
                <strong>{item.metric || item.label || `Item ${idx + 1}`}</strong>
                {item.rationale && <span className="muted"> — {item.rationale}</span>}
                {item.suggested_check && <div className="muted small">建議檢核：{item.suggested_check}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {ragNotes.length > 0 && (
        <section className="report-panel">
          <div className="panel-title">Research Library</div>
          <ul className="analysis-list">
            {ragNotes.map((item: any, idx: number) => (
              <li key={`rag-${idx}`}>
                <strong>{item.title}</strong>
                {item.content && <span className="muted"> — {item.content}</span>}
                {item.tags && <div className="muted small">Tags: {(item.tags || []).join(', ')}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
