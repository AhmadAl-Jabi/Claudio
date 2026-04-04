import { useState, useEffect } from 'react'

export default function TopBar({ feedActive, status }) {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const timeStr = time.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })

  let statusLabel, statusClass
  if (status === 'thinking') {
    statusLabel = 'Thinking...'
    statusClass = 'thinking'
  } else if (feedActive) {
    statusLabel = 'Connected'
    statusClass = 'connected'
  } else {
    statusLabel = 'Waiting for camera'
    statusClass = 'waiting'
  }

  return (
    <div className="top-bar">
      <div className="top-bar-left">
        <span className="logo-text"><span className="logo-accent">C</span>laudio</span>
        <div className="status-pill">
          <span className={`status-dot ${statusClass}`} />
          <span className="status-label">{statusLabel}</span>
        </div>
      </div>
      <div className="top-bar-right">
        <span className="clock">{timeStr}</span>
      </div>
    </div>
  )
}
