import React from 'react'

type Props = { left: React.ReactNode; right: React.ReactNode }

export const Layout: React.FC<Props> = ({ left, right }) => {
  return (
    <div className="app-shell">
      <div className="header">
        <div className="title">VICI Research Agent</div>
        <div className="sub">台股研究 × 瀏覽器擷取 × LLM 分析</div>
      </div>
      <div className="app">
        <div className="sidebar">{left}</div>
        <div className="content">{right}</div>
      </div>
    </div>
  )
}
