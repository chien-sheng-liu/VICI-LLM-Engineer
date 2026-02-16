import React, { useEffect, useState } from 'react'

type RunResult = {
  running: boolean
  status?: string
  error?: string
  report?: string
  slides?: string
  logs?: any[]
  screenshots?: string[]
  runId?: string
  artifacts?: { reportUrl?: string; slidesUrl?: string; screenshots?: string[]; consoleUrl?: string; llmCallsUrl?: string; newsUrl?: string }
  sections?: any
}

export const RunForm: React.FC<{ running?: boolean; onRun: (result: RunResult) => void }> = ({ running, onRun }) => {
  const [ticker, setTicker] = useState('2330')
  const [yahoo, setYahoo] = useState(true)
  const [source, setSource] = useState('https://tw.stock.yahoo.com/')
  const [model, setModel] = useState('gpt-3.5-turbo')
  const [gateway, setGateway] = useState('http://localhost:8000')
  const [claudeReady, setClaudeReady] = useState<boolean | null>(null)
  const [notice, setNotice] = useState<string>('')

  // Load provider status when gateway changes
  useEffect(() => {
    const load = async () => {
      setClaudeReady(null)
      setNotice('')
      const base = gateway.replace(/\/$/, '')
      try {
        const r = await fetch(`${base}/providers/status`)
        if (r.ok) {
          const j = await r.json()
          const ready = !!j?.providers?.claude?.ready
          setClaudeReady(ready)
          if (!ready) setNotice('Claude 不可用，建議改用 OpenAI 或 Mock 模型')
        }
      } catch {
        // ignore
      }
    }
    if (gateway) load()
  }, [gateway])

  const run = async () => {
    onRun({ running: true, status: '啟動中…', error: '' })
    try {
      const chosenModel = (model.startsWith('claude') && claudeReady === false) ? 'gpt-3.5-turbo' : model
      if (model.startsWith('claude') && claudeReady === false) {
        setNotice('Claude 不可用，已自動改用 OpenAI 模型')
      }
      const payload = { ticker, source, model: chosenModel, gateway, dry_run: false, yahoo }
      const resp = await fetch(`${gateway.replace(/\/$/, '')}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!resp.ok) {
        const text = await resp.text()
        onRun({ running: false, error: `啟動失敗 (${resp.status}): ${text}` })
        return
      }
      const data = await resp.json()
      const runId = data.run_id
      onRun({ running: true, status: `Run started: ${runId}`, runId })
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
            artifacts: {
              reportUrl: st.artifacts?.report_url,
              slidesUrl: st.artifacts?.slides_url,
              screenshots: st.screenshots,
              consoleUrl: st.artifacts?.console_url,
              llmCallsUrl: st.artifacts?.llm_calls_url,
              newsUrl: st.artifacts?.news_url,
            },
            sections: st.sections,
          })
        }
      }
    } catch (e: any) {
      onRun({ running: false, error: e?.message || 'Network error' })
      console.error(e)
    }
  }

  return (
    <div className="left-stack">
      <div className="card">
        <div className="section-title">模型與輸入</div>
        <div className="form-grid onecol">
          <div className="field">
            <div className="label">模型</div>
            <select
              className="select"
              value={model}
              onChange={(e) => {
                const v = e.target.value
                if (v.startsWith('claude')) {
                  if (claudeReady === false) {
                    try { window.alert('Claude 不可用，已改用 OpenAI 模型') } catch {}
                    setNotice('Claude 不可用，已改用 OpenAI 模型')
                    setModel('gpt-3.5-turbo')
                    return
                  }
                }
                setNotice('')
                setModel(v)
              }}
            >
              <option value="gpt-3.5-turbo">gpt-3.5-turbo（OpenAI）</option>
              <option value="claude-3-haiku">claude-3-haiku（Claude CLI）</option>
            </select>
          </div>
          {notice && <div className="muted" style={{ fontSize: 12 }}>{notice}</div>}
          <div className="field">
            <div className="label">台股代號</div>
            <input className="input" value={ticker} onChange={(e) => setTicker(e.target.value.trim())} placeholder="2330" />
          </div>
          <div className="field">
            <label className="row" style={{ justifyContent: 'space-between' }}>
              <span className="label">Yahoo 自動化流程</span>
              <input className="checkbox" type="checkbox" checked={yahoo} onChange={(e)=> setYahoo(e.target.checked)} />
            </label>
          </div>
          <div className="field">
            <div className="label">來源網址</div>
            <input className="input" value={source} onChange={(e) => setSource(e.target.value.trim())} placeholder="https://tw.stock.yahoo.com/" disabled={yahoo} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="section-title">連線設定</div>
        <div className="form-grid onecol">
          <div className="field">
            <div className="label">Gateway URL</div>
            <input className="input" value={gateway} onChange={(e) => setGateway(e.target.value.trim())} placeholder="http://localhost:8000" />
          </div>
          <button className="btn" onClick={run} disabled={!!running || !gateway || !ticker || !model}>
            {running ? (<span className="row"><span className="spinner" /> 我要執行分析…</span>) : '執行分析'}
          </button>
        </div>
      </div>

      <div className="muted" style={{ fontSize: 12 }}>
        - 模型可替換（含 Claude CLI 模擬）。<br/>
        - 啟用 Yahoo 自動化時，系統會自動開啟 Yahoo 並搜尋代號。
      </div>
    </div>
  )
}
