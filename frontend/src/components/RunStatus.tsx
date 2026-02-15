import React from 'react'

type Props = {
  running: boolean
  status?: string
  error?: string
}

export const RunStatus: React.FC<Props> = ({ running, status, error }) => {
  return (
    <div style={{ marginBottom: 12 }}>
      <div>{running ? 'Running…' : 'Idle'}</div>
      {status ? <div style={{ color: '#444' }}>{status}</div> : null}
      {error ? <div style={{ color: '#b00020' }}>Error: {error}</div> : null}
    </div>
  )
}
