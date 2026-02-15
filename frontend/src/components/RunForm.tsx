import React, { useState } from 'react'

type RunResult = {
  running: boolean
  report?: string
  slides?: string
  logs?: any[]
  screenshots?: string[]
}

export const RunForm: React.FC<{ onRun: (result: RunResult) => void }> = ({ onRun }) => {
  const [ticker, setTicker] = useState('AAPL')
  const [source, setSource] = useState('https://example.com')
  const [model, setModel] = useState('mock-01')
  const [gateway, setGateway] = useState('http://localhost:8000')
  const [dryRun, setDryRun] = useState(true)

  const run = async () => {
    onRun({ running: true })
    try {
      const resp = await fetch(`${gateway.replace(/\/$/, '')}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, source, model, gateway, dry_run: dryRun }),
      })
      const data = await resp.json()
      const runId = data.run_id
      // poll status
      let done = false
      while (!done) {
        await new Promise((r) => setTimeout(r, 800))
        const s = await fetch(`${gateway.replace(/\/$/, '')}/agent/status/${runId}`)
        const st = await s.json()
        if (st.status === 'completed' || st.status === 'error') {
          done = true
          onRun({
            running: false,
            report: st.report_md_text || '',
            slides: st.artifacts?.slides_url || '',
            logs: [],
            screenshots: st.screenshots || [],
          })
        }
      }
    } catch (e) {
      onRun({ running: false })
      console.error(e)
    }
  }

  return (
    <div>
      <h3>Run Research</h3>
      <div style={{ display: 'grid', gap: 8 }}>
        <label>
          Ticker
          <input value={ticker} onChange={(e) => setTicker(e.target.value)} style={{ width: '100%' }} />
        </label>
        <label>
          Source URL
          <input value={source} onChange={(e) => setSource(e.target.value)} style={{ width: '100%' }} />
        </label>
        <label>
          Model
          <select value={model} onChange={(e) => setModel(e.target.value)} style={{ width: '100%' }}>
            <option value="mock-01">mock-01</option>
            <option value="gpt-3.5-turbo">gpt-3.5-turbo</option>
            <option value="claude-3-haiku">claude-3-haiku</option>
          </select>
        </label>
        <label>
          Gateway URL
          <input value={gateway} onChange={(e) => setGateway(e.target.value)} style={{ width: '100%' }} />
        </label>
        <label>
          Dry Run
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
        </label>
        <button onClick={run}>Run</button>
      </div>
    </div>
  )
}
