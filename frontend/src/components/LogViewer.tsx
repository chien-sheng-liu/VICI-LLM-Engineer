import React from 'react'

type LogItem = {
  request_id?: string
  route?: string
  provider?: string
  model?: string
  latency_ms?: number
  error?: string
}

export const LogViewer: React.FC<{ logs: LogItem[] }> = ({ logs }) => {
  return (
    <div>
      <h3>Logs</h3>
      {logs.length === 0 ? (
        <div>No logs</div>
      ) : (
        <ul>
          {logs.map((l, i) => (
            <li key={i}>
              <code>
                {l.request_id} {l.route} {l.provider} {l.model} {l.latency_ms}ms {l.error ? `error=${l.error}` : ''}
              </code>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

