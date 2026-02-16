import React from 'react'

type Props = { children: React.ReactNode }
type State = { hasError: boolean; error?: any }

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError(error: any) {
    return { hasError: true, error }
  }
  componentDidCatch(error: any, info: any) {
    // noop; could log to server
    console.error('Render error:', error, info)
  }
  render() {
    if (this.state.hasError) {
      return <div className="report-card"><div className="section-title">畫面載入錯誤</div><div className="md">{String(this.state.error?.message || this.state.error || 'Unknown error')}</div></div>
    }
    return this.props.children
  }
}

