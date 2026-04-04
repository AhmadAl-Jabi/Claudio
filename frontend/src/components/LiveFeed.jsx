import { useEffect, useRef } from 'react'

export default function LiveFeed({ onFeedChange }) {
  const imgRef = useRef(null)

  useEffect(() => {
    let active = true
    let prevUrl = null

    async function poll() {
      while (active) {
        try {
          const res = await fetch('/api/frames/live', { cache: 'no-store' })
          if (res.ok) {
            const blob = await res.blob()
            const url = URL.createObjectURL(blob)
            if (imgRef.current) {
              imgRef.current.src = url
              onFeedChange?.(true)
            }
            if (prevUrl) URL.revokeObjectURL(prevUrl)
            prevUrl = url
          }
        } catch {}
        await new Promise(r => setTimeout(r, 100))
      }
    }

    poll()
    return () => {
      active = false
      if (prevUrl) URL.revokeObjectURL(prevUrl)
    }
  }, [])

  return (
    <div className="live-feed">
      <img ref={imgRef} alt="" />
    </div>
  )
}
