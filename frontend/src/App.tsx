import React, { useState } from 'react'
import { Layout } from './components/Layout'
import { RunForm } from './components/RunForm'
import { RunStatus } from './components/RunStatus'
import { LogViewer } from './components/LogViewer'
import { ArtifactViewer } from './components/ArtifactViewer'
import { NewsViewer } from './components/NewsViewer'

export const App: React.FC = () => {
  const [reportContent, setReportContent] = useState<string>('')
  const [logs, setLogs] = useState<any[]>([])
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [tab, setTab] = useState<'Report'|'News'|'Logs'|'History'>('Report')
  const [history, setHistory] = useState<{ runId: string; reportUrl?: string; when: number }[]>([])
  const [openHistory, setOpenHistory] = useState<Record<string, boolean>>({})
  const [consoleUrl, setConsoleUrl] = useState<string | undefined>(undefined)
  const [llmCallsUrl, setLlmCallsUrl] = useState<string | undefined>(undefined)
  const [newsUrl, setNewsUrl] = useState<string | undefined>(undefined)
  const [newsItems, setNewsItems] = useState<{ title: string; url: string; time?: string }[]>([])
  const [sections, setSections] = useState<any | null>(null)

  // Load history from localStorage on mount
  React.useEffect(() => {
    try {
      const raw = localStorage.getItem('runHistory')
      if (raw) {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) setHistory(parsed)
      }
    } catch {}
  }, [])

  // Persist history
  React.useEffect(() => {
    try { localStorage.setItem('runHistory', JSON.stringify(history)) } catch {}
  }, [history])

  // Load news JSON when URL changes
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
      } catch {}
    }
    load()
  }, [newsUrl, sections])

  return (
    <Layout
      left={
        <div>
          <RunForm
            running={running}
            onRun={(res) => {
              setRunning(res.running)
              if (res.running && !res.runId) {
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
                  setSections(res.sections)
                  if (Array.isArray(res.sections.news)) setNewsItems(res.sections.news)
                } else {
                  setSections(null)
                }
              }
            }}
          />
        </div>
      }
      right={
        <div className="container">
          <div className="workspace-card" style={{ marginBottom: 16 }}>
            <div className="section-title">執行狀態</div>
            <div className="status">
              <span className={`dot ${running ? 'running' : (error ? 'error' : 'idle')}`}></span>
              <span>{running ? '執行中' : (error ? '發生錯誤' : '待命')}</span>
              {status && <span className="muted">{status}</span>}
            </div>
          </div>

          <div className="workspace-card">
            <div className="section-title">分析結果</div>
            <div className="tabs">
              {(['Report','News','Logs','History'] as const).map((t) => (
                <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>
              ))}
            </div>
            <div className="tab-panel">
              {tab === 'Report' && (
                <ArtifactViewer sections={sections} reportContent={reportContent} newsItems={newsItems} />
              )}
              {tab === 'News' && (
                <NewsViewer sections={sections} newsItems={newsItems} />
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
          </div>
        </div>
      }
    />
  )
}
