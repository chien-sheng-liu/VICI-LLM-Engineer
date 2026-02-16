import React, { useEffect, useMemo, useState } from 'react'

type NewsItem = { title: string; url: string; time?: string; source?: string }

function sentimentScore(s?: string): number | '-' {
  if (!s) return '-'
  if (s.includes('正')) return 5
  if (s.includes('負')) return 1
  return 3
}

export const NewsViewer: React.FC<{ sections: any | null; newsItems: NewsItem[] }>
  = ({ sections, newsItems }) => {
  const micro = Array.isArray(sections?.news_micro) ? sections!.news_micro : []
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [activeKw, setActiveKw] = useState<string | null>(null)
  // News 視圖不顯示交易綜合分數，避免與 Report 重複

  const byUrl = useMemo(() => {
    const m = new Map<string, NewsItem>()
    for (const n of newsItems || []) if (n.url) m.set(n.url, n)
    return m
  }, [newsItems])

  const hostFromUrl = (url?: string) => {
    if (!url) return ''
    try {
      const u = new URL(url)
      return u.hostname.replace(/^www\./, '')
    } catch {
      return ''
    }
  }

  if (!sections) return <div className="md">尚無資料</div>

  // Sentiment breakdown from micro summaries
  const sentCounts = micro.reduce((acc: any, m: any) => {
    const s = String(m?.sentiment || '')
    if (s.includes('正')) acc.pos += 1
    else if (s.includes('負')) acc.neg += 1
    else acc.neu += 1
    return acc
  }, { pos: 0, neu: 0, neg: 0 })
  const sentTotal = Math.max(1, sentCounts.pos + sentCounts.neu + sentCounts.neg)
  const sentPct = {
    pos: Math.round(sentCounts.pos / sentTotal * 100),
    neu: Math.round(sentCounts.neu / sentTotal * 100),
    neg: Math.round(sentCounts.neg / sentTotal * 100),
  }

  // Source category breakdown from newsItems (fallback heuristics)
  const classify = (src?: string) => {
    const s = String(src || '').toLowerCase()
    if (!s) return 'other'
    if (/(reuters|bloomberg|ft\.com|wsj|cnbc)/.test(s)) return 'international'
    if (/(cnyes|moneydj|udn|yahoo|technews|bnext|ltn|storm|ctee|cmmedia|chinatimes|tw\.stock\.yahoo\.com)/.test(s)) return 'domestic'
    if (/(morganstanley|goldmansachs|jpmorgan|ubs|barclays|nomura|bofa|citigroup|hsbc)/.test(s)) return 'broker'
    return 'other'
  }
  const catCounts = (newsItems || []).reduce((acc: any, n: any) => {
    const cat = String(n?.category || classify(n?.source))
    acc[cat] = (acc[cat] || 0) + 1
    return acc
  }, {})
  const catTotal = Object.values(catCounts).reduce((a: any, b: any) => a + (b as number), 0) || 1
  const catPct = (k: string) => Math.round(((catCounts[k] || 0) as number) / catTotal * 100)

  // Financial keywords hotness from titles + summaries
  const keywords = [
    { k: 'EPS', re: /(eps|盈餘|每股盈餘)/i },
    { k: '毛利', re: /(毛利|gross\s*margin)/i },
    { k: '營收', re: /(營收|revenue|sales)/i },
    { k: 'CapEx', re: /(capex|資本支出|資本開支)/i },
    { k: 'ASP', re: /(asp|平均售價)/i },
    { k: '產能', re: /(產能|capacity|稼動率)/i },
    { k: '目標價', re: /(目標價|target\s*price)/i },
    { k: '庫存', re: /(庫存|inventory)/i },
    { k: '匯率', re: /(匯率|fx|外匯)/i },
    { k: '價格/成本', re: /(價格|cost|成本|pricing)/i },
    { k: '成長', re: /(成長|growth|yoy|qoq)/i },
    { k: '指引', re: /(指引|guidance)/i },
    { k: '估值', re: /(估值|valuation|本益比|pe\b)/i },
    { k: '訂單', re: /(訂單|order|bookings)/i },
  ]
  const kwMap = new Map<string, number>()
  for (const m of micro) {
    const text = `${m?.title || ''} ${m?.summary || ''}`
    for (const kw of keywords) {
      if (kw.re.test(text)) kwMap.set(kw.k, (kwMap.get(kw.k) || 0) + 1)
    }
  }
  const topKw = Array.from(kwMap.entries()).sort((a,b)=> b[1]-a[1]).slice(0,6)

  // Build scored list for top positive/negative
  type Scored = { title: string; url?: string; score: number }
  const scored: Scored[] = micro.map((m:any) => {
    const s = sentimentScore(m.sentiment)
    const c = (typeof m.confidence === 'number') ? m.confidence : undefined
    const mc = (typeof s === 'number' && typeof c === 'number') ? Math.round((s + c) / 2) : (typeof s === 'number' ? s : (typeof c === 'number' ? c : 0))
    return { title: String(m.title || ''), url: m.url, score: mc || 0 }
  })
  const topPos = scored.filter(x => x.title).sort((a,b)=> b.score - a.score).slice(0,2)
  const topNeg = scored.filter(x => x.title).sort((a,b)=> a.score - b.score).slice(0,2)

  // Auto summary lines（僅新聞面，不含交易指標/洞見）
  const autoSummary: string[] = (() => {
    const lines: string[] = []
    lines.push(`今日情緒：正向 ${sentPct.pos}%｜中性 ${sentPct.neu}%｜負向 ${sentPct.neg}%`)
    const k1 = topKw[0]?.[0], k2 = topKw[1]?.[0], k3 = topKw[2]?.[0]
    if (k1) lines.push(`焦點關鍵字：${[k1,k2,k3].filter(Boolean).join('、')}`)
    if (topPos[0]?.title) lines.push(`代表新聞：${topPos[0].title}`)
    // 不顯示交易指標與交易員洞見（改由 Report 呈現）
    // Integrated Sentiment/Surprise goes to the top if available
    if (sections?.sentiment) {
      const s = String(sections.sentiment).replace(/\s+/g,' ').trim()
      const head = s.length > 120 ? (s.slice(0,120) + '…') : s
      lines.unshift(`情緒與驚喜：${head}`)
    }
    return lines.slice(0,4)
  })()

  // Top sources by frequency
  const srcCounts = Array.from((newsItems||[]).reduce((acc: Map<string, number>, n: any) => {
    const s = String(n?.source || '').trim()
    if (!s) return acc
    acc.set(s, (acc.get(s) || 0) + 1)
    return acc
  }, new Map())).sort((a,b)=> b[1]-a[1]).slice(0,4)

  // Determine representative news key (top positive by score, prefer url)
  const repKey: string | null = (topPos[0]?.url ? String(topPos[0].url) : null)

  // Build filtered list once for reuse
  const norm = (s?: string) => String(s || '').toLowerCase()
  const filteredMicro = activeKw
    ? micro.filter((m:any)=> norm(m?.title).includes(norm(activeKw)) || norm(m?.summary).includes(norm(activeKw)))
    : micro

  // Auto-open representative or first filtered item when nothing opened yet
  useEffect(() => {
    const anyOpen = Object.values(open).some(Boolean)
    if (anyOpen) return
    const targetUrl = repKey
    const firstItem = filteredMicro[0]
    const k = (activeKw && firstItem) ? (firstItem.url || null) : targetUrl
    if (k) setOpen((p)=> ({ ...p, [k]: true }))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repKey, activeKw, filteredMicro.length])

  return (
    <div className="news-hud">
      <section className="card news-hero">
        <div className="section-title">Catalyst Briefing</div>
        <ul className="news-list">
          {autoSummary.map((s, i)=>(<li key={i}>{s}</li>))}
        </ul>
      </section>

      <div className="grid-3 news-matrix">
        <section className="card mini">
          <div className="label">情緒分佈</div>
          <div className="barline"><div className="bar pos" style={{ width: `${sentPct.pos}%` }}></div></div>
          <div className="muted" style={{ fontSize:12 }}>正向 {sentPct.pos}%｜中性 {sentPct.neu}%｜負向 {sentPct.neg}%</div>
        </section>
        <section className="card mini">
          <div className="label">來源類別</div>
          <div className="barline"><div className="bar" style={{ width: `${catPct('domestic')}%` }}></div></div>
          <div className="muted" style={{ fontSize:12 }}>國內 {catPct('domestic')}%｜國際 {catPct('international')}%｜券商 {catPct('broker')}%｜其他 {catPct('other')}%</div>
          {srcCounts.length > 0 && (
            <ul className="news-list" style={{ marginTop: 6 }}>{srcCounts.map(([s,c], i)=>(<li key={i}>{s} <span className="muted">×{c}</span></li>))}</ul>
          )}
        </section>
        <section className="card mini">
          <div className="label">財務關鍵字</div>
          <ul className="news-list">
            {topKw.length === 0 ? (<li className="muted">—</li>) : topKw.map(([k,c]) => (
              <li key={k}><span className={`pill clickable ${activeKw===k?'active':''}`} onClick={()=> setActiveKw(k)}>{k}</span> <span className="muted">×{c}</span></li>
            ))}
          </ul>
          {activeKw && (
            <div className="muted" style={{ fontSize:12, marginTop:6 }}>已套用關鍵字：{activeKw} <button className="btn-secondary" style={{ marginLeft:8 }} onClick={()=> setActiveKw(null)}>清除</button></div>
          )}
        </section>
      </div>

      <section className="card timeline-card">
        <div className="section-title">Headline Heat</div>
        <div className="timeline-grid">
          <div>
            <div className="label">Top 正向</div>
            <ul className="news-list">
              {topPos.length === 0 ? (<li className="muted">—</li>) : topPos.map((x, i)=>(
                <li key={`p${i}`}><a href={x.url} target="_blank" rel="noreferrer">{x.title}</a> <span className="muted">｜{x.score}/5</span></li>
              ))}
            </ul>
          </div>
          <div>
            <div className="label">Top 負向</div>
            <ul className="news-list">
              {topNeg.length === 0 ? (<li className="muted">—</li>) : topNeg.map((x, i)=>(
                <li key={`n${i}`}><a href={x.url} target="_blank" rel="noreferrer">{x.title}</a> <span className="muted">｜{x.score}/5</span></li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="card news-feed">
        <div className="section-title">News Tape <span className="pill" title="信心分數由 LLM 與啟發式合成">i</span></div>
        {filteredMicro.length === 0 ? (
          <div>
            <div className="muted">沒有符合「{activeKw}」的新聞</div>
            {activeKw && (<div style={{ marginTop: 6 }}><button className="btn-secondary" onClick={()=> setActiveKw(null)}>清除篩選</button></div>)}
          </div>
        ) : (
          <ul className="timeline">
            {filteredMicro.map((m:any, i:number) => {
              const meta = (m.url && byUrl.get(m.url)) || undefined
              const key = m.url || String(i)
              const isOpen = !!open[key]
              const sc = sentimentScore(m.sentiment)
              const mc = (() => {
                const s = (typeof sc === 'number') ? sc : undefined
                const c = (typeof m.confidence === 'number') ? m.confidence : undefined
                if (typeof s === 'number' && typeof c === 'number') return Math.max(1, Math.min(5, Math.round((s + c) / 2)))
                if (typeof s === 'number') return s
                if (typeof c === 'number') return c
                return undefined
              })()
              const badgeCls = mc ? (mc >=4 ? 'score-good' : (mc>=3 ? 'score-mid' : 'score-poor')) : 'score-mid'
              const origin = meta?.source || hostFromUrl(m.url)
              return (
                <li key={key} className="timeline-item">
                  <div className="timeline-head">
                    <div>
                      <a href={m.url} target="_blank" rel="noreferrer">{m.title}</a> {repKey && key===repKey && (<span className="pill">代表</span>)}
                      <div className="meta-line">
                        {origin && (<span className="pill meta">{origin}</span>)}
                        {meta?.time && (<span className="pill meta">{meta.time}</span>)}
                        {m.type && (<span className="pill meta ghost">{m.type}</span>)}
                      </div>
                    </div>
                    <div className="row">
                      <div className={`score-badge score-badge-sm ${badgeCls}`}>{mc ? `${mc}/5` : '—'}</div>
                      <button className={`btn-secondary ${isOpen ? 'active' : ''}`} onClick={() => setOpen((p)=>({ ...p, [key]: !isOpen }))}>{isOpen ? '收合' : '展開'}</button>
                    </div>
                  </div>
                  {isOpen && (
                    <div className="timeline-body">
                      <div className="md" style={{ fontSize: 14 }}>{m.summary || '—'}</div>
                      {m.market_note && (<div className="muted" style={{ marginTop:6, fontSize:13 }}>市場註解：{m.market_note}</div>)}
                      {m.kpi_impact && (
                        <div style={{ marginTop:6 }}>
                          {(m.kpi_impact.revenue?.direction) && (<span className="pill">營收{m.kpi_impact.revenue.direction==='上'?'↗︎':(m.kpi_impact.revenue.direction==='下'?'↘︎':'→')}</span>)}
                          {(m.kpi_impact.gross_margin?.direction) && (<span className="pill">毛利{m.kpi_impact.gross_margin.direction==='上'?'↗︎':(m.kpi_impact.gross_margin.direction==='下'?'↘︎':'→')}</span>)}
                          {(m.kpi_impact.eps?.direction) && (<span className="pill">EPS{m.kpi_impact.eps.direction==='上'?'↗︎':(m.kpi_impact.eps.direction==='下'?'↘︎':'→')}</span>)}
                        </div>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
