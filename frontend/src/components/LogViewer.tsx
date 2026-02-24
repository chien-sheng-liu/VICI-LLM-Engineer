import React, { useEffect, useState } from 'react'

type LogItem = {
  request_id?: string
  route?: string
  provider?: string
  model?: string
  latency_ms?: number
  error?: string
}

export const LogViewer: React.FC<{ logs: LogItem[]; consoleUrl?: string; llmCallsUrl?: string }> = ({ logs, consoleUrl, llmCallsUrl }) => {
  const [consoleText, setConsoleText] = useState<string>('')
  const [calls, setCalls] = useState<any[]>([])

  useEffect(() => {
    const load = async () => {
      try {
        if (consoleUrl) {
          const r = await fetch(consoleUrl)
          if (r.ok) setConsoleText(await r.text())
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('Failed to load console logs', e)
      }
      try {
        if (llmCallsUrl) {
          const r = await fetch(llmCallsUrl)
          if (r.ok) {
            const text = await r.text()
            const lines = text.split(/\r?\n/).filter(Boolean)
            setCalls(lines.map((l) => { try { return JSON.parse(l) } catch { return { raw: l } } }))
          }
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('Failed to load LLM calls', e)
      }
    }
    load()
  }, [consoleUrl, llmCallsUrl])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div>
        <div className="label">Gateway Requests</div>
        {logs.length === 0 ? (
          <div className="muted">No logs</div>
        ) : (
          <ul>
            {logs.map((l, i) => (
              <li key={i}>
                <code>
                  {l.request_id} {l.route} {l.provider} {l.model} {l.latency_ms}ms {l.error ? `error=${l.error}` : ''}
                </code>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <div className="label">LLM Calls (jsonl)</div>
        {calls.length === 0 ? <div className="muted">No LLM calls</div> : (
          <ul>
            {calls.map((c, i) => (
              <li key={i}><code>{c.category || c.raw} — {c.request_id || ''} {typeof c.latency_ms !== 'undefined' ? `${c.latency_ms}ms` : ''}</code></li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <div className="label">Browser Console</div>
        <pre className="md" style={{ background: '#0c1117', border: '1px solid #1f2937', borderRadius: 8, padding: 12 }}>{consoleText || 'No console output'}</pre>
      </div>
    </div>
  )
}
