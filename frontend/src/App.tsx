import React, { useState } from 'react'
import { Layout } from './components/Layout'
import { RunForm } from './components/RunForm'
import { LogViewer } from './components/LogViewer'
import { ArtifactViewer } from './components/ArtifactViewer'
import { NewsViewer } from './components/NewsViewer'
import { AnalysisViewer } from './components/AnalysisViewer'
import { ErrorBoundary } from './components/ErrorBoundary'

export const App: React.FC = () => {
  const [reportContent, setReportContent] = useState<string>('')
  const [logs, setLogs] = useState<any[]>([])
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [tab, setTab] = useState<'Analysis' | 'Report' | 'News' | 'Logs' | 'History'>('Analysis')
  const [history, setHistory] = useState<{ runId: string; reportUrl?: string; when: number }[]>([])
  const [openHistory, setOpenHistory] = useState<Record<string, boolean>>({})
  const [consoleUrl, setConsoleUrl] = useState<string | undefined>(undefined)
  const [llmCallsUrl, setLlmCallsUrl] = useState<string | undefined>(undefined)
  const [newsUrl, setNewsUrl] = useState<string | undefined>(undefined)
  const [newsItems, setNewsItems] = useState<{ title: string; url: string; time?: string }[]>([])
  const [sections, setSections] = useState<any | null>(null)
  const [contextMeta, setContextMeta] = useState({ ticker: '—', model: '—', source: '—', company: '—' })
  const [analysisUnlocked, setAnalysisUnlocked] = useState(false)
  const analysisSections = sections?.report_sections || sections || null
  const hasResults = !!(analysisSections && Object.keys(analysisSections).length > 0)
  const activeTicker = (analysisSections?.ticker || contextMeta.ticker || '—').toUpperCase()
  const activeSource = analysisSections?.source || contextMeta.source || '尚未啟動'
  const activeModel = analysisSections?.model || contextMeta.model || '尚未啟動'
  const activeCompany = analysisSections?.company_name || contextMeta.company || '尚未取得'

  React.useEffect(() => {
    try {
      const raw = localStorage.getItem('runHistory')
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) setHistory(parsed)
      }
    } catch (e) {
      // Fallback silently if localStorage unavailable
      // eslint-disable-next-line no-console
      console.warn('Failed to read runHistory from localStorage', e)
    }
  }, [])

  React.useEffect(() => {
    try {
      localStorage.setItem('runHistory', JSON.stringify(history))
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn('Failed to persist runHistory', e)
    }
  }, [history])

  React.useEffect(() => {
    if (sections?.news && Array.isArray(sections.news)) {
      setNewsItems(sections.news)
      return
    }
    const load = async () => {
      if (!newsUrl) { setNewsItems([]); return }
      try {
        const r = await fetch(newsUrl)
        if (r.ok) {
          const j = await r.json()
          if (Array.isArray(j)) setNewsItems(j)
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('Failed to load news items', e)
      }
    }
    load()
  }, [newsUrl, sections])

  const heroHeader = (
    <div className="hero-header">
      <div className="hero-copy">
        <p className="eyebrow">操作指南</p>
        <h1>完成 STEP 01 / STEP 02，按下「開始研究」即可啟動研究流程</h1>
        <p>系統會自動觸發瀏覽器代理人蒐集資料，結束後會同步更新 Analysis、Report、News 與 History。</p>
      </div>
      <div className="hero-status">
        <div className={`status-chip large ${running ? 'running' : (error ? 'error' : 'idle')}`}>
          <span className="chip-dot" />
          {running ? '代理人執行中' : (error ? `需要注意：${error}` : (status || '待命中'))}
        </div>
        <div className="hero-meta-grid">
          <div>
            <div className="label">Ticker</div>
            <div className="value">{activeTicker}</div>
          </div>
          <div>
            <div className="label">Model</div>
            <div className="value">{activeModel}</div>
          </div>
          <div>
            <div className="label">Source</div>
            <div className="value ellipsis" title={activeSource}>{activeSource}</div>
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <>
    {heroHeader}
    <Layout
      left={
        <RunForm
          running={running}
          onRun={(res) => {
              setRunning(res.running)
            if (res.running && !res.runId) {
              setAnalysisUnlocked(true)
              setSections(null)
              setNewsItems([])
              setNewsUrl(undefined)
            }
            if (res.status) setStatus(res.status)
            if (res.error) setError(res.error)
            if (res.report) setReportContent(res.report)
            if (res.logs) setLogs(res.logs)
            if (!res.running && res.runId) {
                setHistory((prev) => [{ runId: res.runId!, reportUrl: res.artifacts?.reportUrl, when: Date.now() }, ...prev].slice(0, 20))
                setConsoleUrl(res.artifacts?.consoleUrl)
                setLlmCallsUrl(res.artifacts?.llmCallsUrl)
                setNewsUrl(res.artifacts?.newsUrl)
                if (res.sections) {
                  setSections(res.sections || {})
                  const s = res.sections || {}
                  setContextMeta({
                    ticker: s.ticker || contextMeta.ticker,
                    model: s.model || contextMeta.model,
                    source: s.source || contextMeta.source,
                    company: s.company_name || contextMeta.company,
                  })
                  if (Array.isArray(res.sections.news)) setNewsItems(res.sections.news)
                } else {
                  setSections({})
              }
            }
          }}
          onContextChange={(meta) => setContextMeta((prev) => ({
            ticker: meta.ticker || prev.ticker,
            model: meta.model || prev.model,
            source: meta.source || prev.source,
            company: prev.company,
          }))}
        />
      }
      right={
        <div className="container vertical-flow">
          {analysisUnlocked ? (
            <>
              <div className="workspace-card">
                <div className="section-title">分析結果</div>
                <div className="analysis-meta">
                  <div className="meta-block">
                    <div className="label">Ticker</div>
                    <div className="value">{activeTicker}</div>
                  </div>
                  <div className="meta-block">
                    <div className="label">Company</div>
                    <div className="value ellipsis" title={activeCompany}>{activeCompany}</div>
                  </div>
                  <div className="meta-block">
                    <div className="label">Model</div>
                    <div className="value">{activeModel}</div>
                  </div>
                  <div className="meta-block">
                    <div className="label">Source</div>
                    <div className="value ellipsis" title={activeSource}>{activeSource}</div>
                  </div>
                </div>
            <div className="tabs">
              {(['Analysis','Report','News','Logs','History'] as const).map((t) => (
                <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>
              ))}
            </div>
            {hasResults ? (
              <div className="tab-panel">
                {tab === 'Analysis' && (
                  <AnalysisViewer sections={analysisSections} />
                )}
                {tab === 'Report' && (
                  <ArtifactViewer sections={analysisSections} reportContent={reportContent} />
                )}
                    {tab === 'News' && (
                      <ErrorBoundary>
                        <NewsViewer sections={analysisSections} newsItems={Array.isArray(newsItems) ? newsItems : []} />
                      </ErrorBoundary>
                    )}
                    {tab === 'Logs' && (
                      <LogViewer logs={logs} consoleUrl={consoleUrl} llmCallsUrl={llmCallsUrl} />
                    )}
                    {tab === 'History' && (
                      <div className="history-list">
                        {history.length === 0 ? (
                          <div className="muted">尚無紀錄</div>
                        ) : history.map((h) => {
                          const open = !!openHistory[h.runId]
                          return (
                            <div key={h.runId} className="history-item">
                              <div className="row" style={{ justifyContent: 'space-between' }}>
                                <div className="kv" style={{ gridTemplateColumns: '100px 1fr' }}>
                                  <div className="k">Run ID</div>
                                  <div>{h.runId}</div>
                                </div>
                                <button className="btn-secondary" onClick={() => setOpenHistory((p) => ({ ...p, [h.runId]: !open }))}>{open ? '收合' : '展開'}</button>
                              </div>
                              {open && (
                                <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
                                  <div className="kv"><div className="k">Report</div><div>{h.reportUrl ? <a href={h.reportUrl} target="_blank" rel="noreferrer">開啟報告</a> : <span className="muted">-</span>}</div></div>
                                  <div className="kv"><div className="k">時間</div><div>{new Date(h.when).toLocaleString()}</div></div>
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="tab-panel placeholder">
                    <h4>尚未執行分析</h4>
                    <p>請完成 STEP 02 並啟動代理人，任務完成後將自動顯示最新報告。</p>
                  </div>
                )}
              </div>

              <details className="recent-accordion">
                <summary>最近執行紀錄</summary>
                <div className="recent-panel">
                  {history.length === 0 ? (
                    <div className="muted">尚無紀錄</div>
                  ) : (
                    <ul className="recent-list">
                      {history.slice(0, 4).map((h) => (
                        <li key={`recent-${h.runId}`}>
                          <div>
                            <strong>{h.runId.slice(0, 8)}</strong>
                            <div className="muted" style={{ fontSize: 12 }}>{new Date(h.when).toLocaleTimeString()}</div>
                          </div>
                          <div>
                            {h.reportUrl ? <a href={h.reportUrl} target="_blank" rel="noreferrer">報告</a> : <span className="muted">-</span>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  <button className="btn-secondary" style={{ marginTop: 10 }} onClick={() => setTab('History')}>檢視全部</button>
                </div>
              </details>
            </>
          ) : (
            <div className="workspace-card placeholder">
              <div className="eyebrow">操作提示</div>
              <h4>請先完成 STEP 02</h4>
              <p>完成輸入後，於 STEP 02 按下「開始研究」，系統將自動生成分析結果並解鎖報告、新聞與歷史紀錄。</p>
            </div>
          )}
        </div>
      }
    />
    {running && (
      <div className="processing-overlay" role="alert" aria-live="assertive">
        <div className="processing-box">
          <div className="processing-spinner" />
          <div>
            <div className="eyebrow" style={{ textAlign: 'center' }}>分析進行中</div>
            <h3>代理人正在收集資料</h3>
            <p className="muted">已啟動瀏覽器與 LLM，請稍候片刻，完成後將自動顯示分析結果。</p>
          </div>
        </div>
      </div>
    )}
    </>
  )
}
