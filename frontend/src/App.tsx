import React, { useState } from 'react'
import { Layout } from './components/Layout'
import { RunForm } from './components/RunForm'
import { RunStatus } from './components/RunStatus'
import { LogViewer } from './components/LogViewer'

export const App: React.FC = () => {
  const [reportContent, setReportContent] = useState<string>('')
  const [slidesUrl, setSlidesUrl] = useState<string>('')
  const [logs, setLogs] = useState<any[]>([])
  const [screenshots, setScreenshots] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [status, setStatus] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [tab, setTab] = useState<'Report'|'Slides'|'Screenshots'|'Logs'>('Report')
  const [history, setHistory] = useState<{ runId: string; reportUrl?: string; slidesUrl?: string; screenshots?: string[]; when: number }[]>([])

  return (
    <Layout
      left={
        <>
          <RunForm
            onRun={(res) => {
              setRunning(res.running)
              if (res.status) setStatus(res.status)
              if (res.error) setError(res.error)
              if (res.report) setReportContent(res.report)
              if (res.slides) setSlidesUrl(res.slides)
              if (res.logs) setLogs(res.logs)
              if (res.screenshots) setScreenshots(res.screenshots)
              if (!res.running && res.runId) {
                setHistory((prev) => [{ runId: res.runId!, reportUrl: res.artifacts?.reportUrl, slidesUrl: res.artifacts?.slidesUrl, screenshots: res.artifacts?.screenshots, when: Date.now() }, ...prev].slice(0, 10))
              }
            }}
          />
          <div className="card">
            <div className="label" style={{ marginBottom: 8 }}>Run History</div>
            {history.length === 0 ? (
              <div className="muted">No runs yet.</div>
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {history.map((h) => (
                  <div key={h.runId} style={{ display: 'grid', gap: 6 }}>
                    <div className="kv"><div className="k">Run ID</div><div>{h.runId}</div></div>
                    <div className="kv"><div className="k">Report</div><div>{h.reportUrl ? <a href={h.reportUrl} target="_blank">Open report</a> : <span className="muted">-</span>}</div></div>
                    <div className="kv"><div className="k">Slides</div><div>{h.slidesUrl ? <a href={h.slidesUrl} target="_blank">Open slides</a> : <span className="muted">-</span>}</div></div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      }
      right={
        <div className="container">
          <div className="status" style={{ marginBottom: 12 }}>
            <span className={`dot ${running ? 'running' : (error ? 'error' : 'idle')}`}></span>
            <span>{running ? 'Running…' : (error ? 'Error' : 'Idle')}</span>
            {status && <span className="muted">{status}</span>}
          </div>

          <div className="tabs">
            {(['Report','Slides','Screenshots','Logs'] as const).map((t) => (
              <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>
            ))}
          </div>
          <div className="tab-panel">
            {tab === 'Report' && (
              <div className="md">{reportContent || 'No report yet.'}</div>
            )}
            {tab === 'Slides' && (
              slidesUrl ? (
                <div>
                  <div style={{ marginBottom: 8 }}><a href={slidesUrl} target="_blank">Open slides</a></div>
                  <iframe src={slidesUrl} style={{ width: '100%', height: 600, border: '1px solid #1f2937', borderRadius: 8 }} />
                </div>
              ) : <div className="muted">No slides yet.</div>
            )}
            {tab === 'Screenshots' && (
              <div className="shots">
                {screenshots && screenshots.length > 0 ? screenshots.map((s, i) => (
                  <div key={i} className="shot"><img src={s} alt={`screenshot-${i}`} /></div>
                )) : <div className="muted">No screenshots yet.</div>}
              </div>
            )}
            {tab === 'Logs' && (
              <LogViewer logs={logs} />
            )}
          </div>
        </div>
      }
    />
  )
}
