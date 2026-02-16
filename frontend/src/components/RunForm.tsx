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

type RunFormProps = {
  running?: boolean
  onRun: (result: RunResult) => void
  onContextChange?: (meta: { ticker: string; model: string; source: string }) => void
}

export const RunForm: React.FC<RunFormProps> = ({ running, onRun, onContextChange }) => {
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

  React.useEffect(() => {
    onContextChange?.({ ticker, model, source: yahoo ? 'Yahoo TW Flow' : source })
  }, [ticker, model, source, yahoo, onContextChange])

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
      <section className="card run-card">
        <div className="form-header">
          <div>
            <div className="eyebrow">STEP 01</div>
            <h3>模型與輸入</h3>
            <p className="form-sub">挑選模型與來源，決定是否使用 Yahoo TW 自動化流程。</p>
          </div>
        </div>
        <div className="form-body two-cols">
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
            {notice && <div className="form-note warning">{notice}</div>}
          </div>
          <div className="field">
            <div className="label">台股代號</div>
            <input className="input" value={ticker} onChange={(e) => setTicker(e.target.value.trim())} placeholder="2330" />
            <div className="form-note">支援 Yahoo TW 流程與一般網址。</div>
          </div>
          <div className="field full">
            <div className="toggle-row">
              <div>
                <div className="label">Yahoo 自動化</div>
                <div className="form-note">自動搜尋並導向股票頁，不需自行輸入網址。</div>
              </div>
              <label className="toggle">
                <input type="checkbox" checked={yahoo} onChange={(e)=> setYahoo(e.target.checked)} />
                <span className="slider" />
              </label>
            </div>
          </div>
          <div className="field full">
            <div className="label">來源網址</div>
            <input className="input" value={source} onChange={(e) => setSource(e.target.value.trim())} placeholder="https://tw.stock.yahoo.com/" disabled={yahoo} />
          </div>
        </div>
      </section>

      <section className="card run-card">
        <div className="form-header">
          <div>
            <div className="eyebrow">STEP 02</div>
            <h3>連線設定</h3>
            <p className="form-sub">指定要連線的 Gateway 位置，確保後端已啟動。</p>
          </div>
        </div>
        <div className="form-body">
          <div className="field">
            <div className="label">Gateway URL</div>
            <input className="input" value={gateway} onChange={(e) => setGateway(e.target.value.trim())} placeholder="http://localhost:8000" />
          </div>
          <button className="btn run-btn" onClick={run} disabled={!!running || !gateway || !ticker || !model}>
            {running ? (<span className="row"><span className="spinner" /> 執行中…</span>) : '開始研究'}
          </button>
        </div>
      </section>

      <div className="form-note muted">
        • 模型可隨時更換（含 Claude CLI 模擬）。<br/>
        • 啟用 Yahoo 自動化時會自動開啟 Yahoo 並搜尋代號。
      </div>
    </div>
  )
}
