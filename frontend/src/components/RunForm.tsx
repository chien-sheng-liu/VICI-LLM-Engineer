import React, { useState } from 'react'

type RunResult = {
  running: boolean
  status?: string
  error?: string
  report?: string
  slides?: string
  logs?: any[]
  screenshots?: string[]
  runId?: string
  artifacts?: { reportUrl?: string; slidesUrl?: string; screenshots?: string[] }
}

export const RunForm: React.FC<{ onRun: (result: RunResult) => void }> = ({ onRun }) => {
  const [ticker, setTicker] = useState('AAPL')
  const [source, setSource] = useState('http://localhost:8000/static/sample_ir.html')
  const [model, setModel] = useState('gpt-3.5-turbo')
  const [gateway, setGateway] = useState('http://localhost:8000')
  const [dryRun, setDryRun] = useState(true)

  const run = async () => {
    onRun({ running: true, status: 'Starting run…', error: '' })
    try {
      const resp = await fetch(`${gateway.replace(/\/$/, '')}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, source, model, gateway, dry_run: dryRun }),
      })
      if (!resp.ok) {
        const text = await resp.text()
        onRun({ running: false, error: `Start failed (${resp.status}): ${text}` })
        return
      }
      const data = await resp.json()
      const runId = data.run_id
      onRun({ running: true, status: `Run started: ${runId}`, runId })
      // poll status
      let done = false
      while (!done) {
        await new Promise((r) => setTimeout(r, 800))
        const s = await fetch(`${gateway.replace(/\/$/, '')}/agent/status/${runId}`)
        if (!s.ok) {
          const text = await s.text()
          onRun({ running: false, error: `Status failed (${s.status}): ${text}` })
          return
        }
        const st = await s.json()
        onRun({ running: true, status: `Status: ${st.status}`, runId })
        if (st.status === 'completed' || st.status === 'error') {
          done = true
          onRun({
            running: false,
            status: st.status,
            error: st.status === 'error' ? 'Run failed' : '',
            report: st.report_md_text || '',
            slides: st.artifacts?.slides_url || '',
            logs: [],
            screenshots: st.screenshots || [],
            runId,
            artifacts: { reportUrl: st.artifacts?.report_url, slidesUrl: st.artifacts?.slides_url, screenshots: st.screenshots },
          })
        }
      }
    } catch (e: any) {
      onRun({ running: false, error: e?.message || 'Network error' })
      console.error(e)
    }
  }

  const sampleUrl = 'http://localhost:8000/static/sample_ir.html'
  const useSample = () => setSource(sampleUrl)
  const copySample = async () => {
    try {
      await navigator.clipboard.writeText(sampleUrl)
      onRun({ running: false, status: 'Copied sample URL to clipboard' })
    } catch {
      onRun({ running: false, status: 'Copy failed — select and copy manually' })
    }
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="field">
          <div className="label">Ticker</div>
          <input className="input" value={ticker} onChange={(e) => setTicker(e.target.value)} placeholder="e.g., AAPL" />
        </div>
        <div className="field">
          <div className="label">Source URL</div>
          <div className="row">
            <input className="input" value={source} onChange={(e) => setSource(e.target.value)} placeholder="http://..." />
            <button type="button" className="btn-secondary" onClick={useSample}>Use Sample</button>
            <button type="button" className="btn-secondary" onClick={copySample}>Copy</button>
          </div>
        </div>
        <div className="field">
          <div className="label">Model</div>
          <select className="select" value={model} onChange={(e) => setModel(e.target.value)}>
            <option value="gpt-3.5-turbo">gpt-3.5-turbo</option>
          </select>
        </div>
        <div className="field">
          <div className="label">Gateway URL</div>
          <input className="input" value={gateway} onChange={(e) => setGateway(e.target.value)} placeholder="http://localhost:8000" />
        </div>
        <div className="field" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input className="checkbox" id="dry" type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          <label htmlFor="dry" className="label" style={{ margin: 0 }}>Dry Run (deterministic)</label>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={run} disabled={!gateway || !source || !ticker || !model}>Run</button>
        </div>
      </div>
      <div className="muted" style={{ fontSize: 12 }}>Tip: Use the built-in sample page: {sampleUrl}</div>
    </div>
  )
}
