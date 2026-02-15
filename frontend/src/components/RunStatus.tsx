import React from 'react'

export const RunStatus: React.FC<{ running: boolean }> = ({ running }) => {
  return <div style={{ marginBottom: 12 }}>{running ? 'Running…' : 'Idle'}</div>
}

