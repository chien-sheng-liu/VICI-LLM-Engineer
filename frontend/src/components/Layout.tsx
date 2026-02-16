import React from 'react'

type Props = { left: React.ReactNode; right: React.ReactNode }

export const Layout: React.FC<Props> = ({ left, right }) => {
  return (
    <div className="app-shell">
      <div className="header">
        <div className="title">VICI Research Agent</div>
        <div className="sub">台股研究 × 瀏覽器擷取 × LLM 分析</div>
      </div>
      <div className="page-stack">
        <section className="panel intro-panel">{left}</section>
        <section className="panel main-panel">{right}</section>
      </div>
    </div>
  )
}
