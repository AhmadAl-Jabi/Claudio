import { useState } from 'react'
import FrameThumbnail from './FrameThumbnail'

export default function MessageBubble({ message }) {
  const { role, text, bestFrame, allFrames } = message

  return (
    <div className={`message ${role}`}>
      <div className="bubble">
        <p>{text}</p>
        {bestFrame && bestFrame.image_url && (
          <FrameThumbnail frame={bestFrame} />
        )}
        {allFrames && allFrames.length > 1 && (
          <div className="frame-carousel">
            {allFrames.map((frame, i) => (
              <FrameThumbnail key={i} frame={frame} small />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
