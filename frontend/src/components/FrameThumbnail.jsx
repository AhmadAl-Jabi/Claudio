import { useState } from 'react'

export default function FrameThumbnail({ frame, small }) {
  const [expanded, setExpanded] = useState(false)

  const timeAgo = frame.timestamp
    ? formatTimeAgo(frame.timestamp)
    : null

  return (
    <>
      <div
        className={`frame-thumb ${small ? 'small' : ''}`}
        onClick={() => setExpanded(true)}
      >
        <img src={frame.image_url} alt="Matched frame" />
        {timeAgo && <span className="frame-time">{timeAgo}</span>}
      </div>

      {expanded && (
        <div className="frame-overlay" onClick={() => setExpanded(false)}>
          <div className="frame-overlay-content">
            <img src={frame.image_url} alt="Matched frame" />
            {timeAgo && <p className="frame-overlay-time">{timeAgo}</p>}
          </div>
        </div>
      )}
    </>
  )
}

function formatTimeAgo(timestamp) {
  const diff = Date.now() - new Date(timestamp).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h ${mins % 60}m ago`
}
