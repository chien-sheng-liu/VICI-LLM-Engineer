import React, { useMemo, useState } from 'react'

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

  const byUrl = useMemo(() => {
    const m = new Map<string, NewsItem>()
    for (const n of newsItems || []) if (n.url) m.set(n.url, n)
    return m
  }, [newsItems])

  if (!sections) return <div className="md">尚無資料</div>

  return (
    <div className="report-layout">
      <div className="report-card">
        <div className="section-title">新聞列表（逐則總結） <span className="pill" title="信心分數由 LLM 與啟發式合成">i</span></div>
        {micro.length === 0 ? (
          <div className="muted">尚無新聞摘要</div>
        ) : (
          <ul className="history-list" style={{ marginTop: 8 }}>
            {micro.map((m:any, i:number) => {
              const meta = (m.url && byUrl.get(m.url)) || undefined
              const key = m.url || String(i)
              const isOpen = !!open[key]
              const sc = sentimentScore(m.sentiment)
              return (
                <li key={key} className="history-item">
                  <div className="row" style={{ justifyContent:'space-between' }}>
                    <div style={{ display:'grid', gap:4 }}>
                      <div className="md" style={{ fontWeight:600 }}>
                        <a href={m.url} target="_blank" rel="noreferrer">{m.title}</a>
                      </div>
                      <div className="muted" style={{ fontSize:12 }}>
                        {(meta?.source || '')} {meta?.time ? `｜${meta.time}` : ''}
                        {m.type ? ` ｜ 類型：${m.type}` : ''}
                        {m.sentiment ? ` ｜ 情緒：${m.sentiment}` : ''}
                        {typeof sc === 'number' ? ` ｜ 情緒分數：${sc}/5` : ''}
                        {typeof m.confidence === 'number' ? ` ｜ 信心：${m.confidence}/5` : ''}
                      </div>
                    </div>
                    <button className={`btn-secondary ${isOpen ? 'active' : ''}`} onClick={() => setOpen((p)=>({ ...p, [key]: !isOpen }))}>{isOpen ? '收合' : '展開'}</button>
                  </div>
                  {isOpen && (
                    <div style={{ marginTop:8 }}>
                      <div className="md">{m.summary || '—'}</div>
                      {m.market_note && (<div className="muted" style={{ marginTop:6 }}>市場註解：{m.market_note}</div>)}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
