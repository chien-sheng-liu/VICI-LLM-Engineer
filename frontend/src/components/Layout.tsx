import React from 'react'

type Props = {
  left: React.ReactNode
  right: React.ReactNode
}

export const Layout: React.FC<Props> = ({ left, right }) => {
  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'sans-serif' }}>
      <div style={{ width: 360, borderRight: '1px solid #e5e5e5', padding: 16 }}>{left}</div>
      <div style={{ flex: 1 }}>{right}</div>
    </div>
  )
}

