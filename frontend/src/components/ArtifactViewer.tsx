import React from 'react'

type Props = {
  reportContent: string
  slidesUrl?: string
  screenshots: string[]
}

export const ArtifactViewer: React.FC<Props> = ({ reportContent, slidesUrl, screenshots }) => {
  return (
    <div>
      <h3>Report</h3>
      <pre style={{ whiteSpace: 'pre-wrap', background: '#fafafa', padding: 12 }}>{reportContent}</pre>
      <h3>Slides</h3>
      {slidesUrl ? <a href={slidesUrl} target="_blank">Open PDF</a> : <div>No slides available</div>}
      <h3>Screenshots</h3>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {screenshots.map((s, i) => (
          <img key={i} src={s} style={{ width: 200, border: '1px solid #eee' }} />
        ))}
      </div>
    </div>
  )
}

