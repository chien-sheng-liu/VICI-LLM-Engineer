import React, { useState } from 'react'
import { Layout } from './components/Layout'
import { RunForm } from './components/RunForm'
import { RunStatus } from './components/RunStatus'
import { ArtifactViewer } from './components/ArtifactViewer'
import { LogViewer } from './components/LogViewer'

export const App: React.FC = () => {
  const [reportContent, setReportContent] = useState<string>('')
  const [slidesUrl, setSlidesUrl] = useState<string>('')
  const [logs, setLogs] = useState<any[]>([])
  const [screenshots, setScreenshots] = useState<string[]>([])
  const [running, setRunning] = useState(false)

  return (
    <Layout
      left={
        <RunForm
          onRun={(status) => {
            setRunning(status.running)
            if (status.report) setReportContent(status.report)
            if (status.slides) setSlidesUrl(status.slides)
            if (status.logs) setLogs(status.logs)
            if (status.screenshots) setScreenshots(status.screenshots)
          }}
        />
      }
      right={
        <div style={{ padding: 16 }}>
          <RunStatus running={running} />
          <ArtifactViewer reportContent={reportContent} slidesUrl={slidesUrl} screenshots={screenshots} />
          <LogViewer logs={logs} />
        </div>
      }
    />
  )
}

