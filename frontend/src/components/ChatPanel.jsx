import { useState, useRef, useEffect, useCallback } from 'react'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'

// Single persistent audio element — must be unlocked during a user gesture
// before Chrome will allow programmatic playback from WebSocket events.
const _audioEl = new Audio()
let _audioUnlocked = false

function _unlockAudio() {
  if (_audioUnlocked) return
  _audioUnlocked = true
  // Play a silent 0-length wav to satisfy Chrome's autoplay requirement
  _audioEl.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA='
  _audioEl.play().catch(() => {})
}

// Unlock on the earliest possible user interaction with the page
document.addEventListener('pointerdown', _unlockAudio, { once: true })
document.addEventListener('keydown', _unlockAudio, { once: true })

async function playTTS(text) {
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!res.ok) return

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    _audioEl.onended = () => URL.revokeObjectURL(url)
    _audioEl.onerror = () => URL.revokeObjectURL(url)
    _audioEl.src = url
    _audioEl.load()
    _audioEl.play().catch(() => {})
  } catch {}
}

export default function ChatPanel({ onStatusChange }) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  // null = not listening; string = live transcription in progress
  const [liveTranscript, setLiveTranscript] = useState(null)
  const scrollRef = useRef(null)
  const wsRef = useRef(null)

  // Auto-scroll whenever content changes
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading, liveTranscript])

  // Voice WebSocket — relay events from phone → laptop UI
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${proto}//${window.location.host}/ws/voice`

    function connect() {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onmessage = (event) => {
        let msg
        try { msg = JSON.parse(event.data) } catch { return }

        if (msg.type === 'interim') {
          // Grow the live transcript bubble in real time
          setLiveTranscript(msg.text || '')
        } else if (msg.type === 'question') {
          // Speech finished — lock it in as a user message
          setLiveTranscript(null)
          setMessages(prev => [...prev, { role: 'user', text: msg.text }])
          setLoading(true)
          onStatusChange?.('thinking')
        } else if (msg.type === 'thinking') {
          setLoading(true)
          onStatusChange?.('thinking')
        } else if (msg.type === 'answer') {
          setLoading(false)
          onStatusChange?.('idle')
          setMessages(prev => [...prev, {
            role: 'assistant',
            text: msg.answer,
            bestFrame: msg.best_frame,
            allFrames: msg.all_frames,
          }])
          if (msg.answer) playTTS(msg.answer)
        }
      }

      ws.onclose = () => setTimeout(connect, 1500)
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null  // prevent reconnect loop on unmount
        wsRef.current.close()
      }
    }
  }, [onStatusChange])

  // Typed / desktop queries still go through the HTTP endpoint
  async function handleSend(text) {
    setMessages(prev => [...prev, { role: 'user', text }])
    setLoading(true)
    onStatusChange?.('thinking')
    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: data.answer,
        bestFrame: data.best_frame,
        allFrames: data.all_frames,
      }])
      if (data.answer) playTTS(data.answer)
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: "I'm having trouble right now. Is the camera connected?",
      }])
    } finally {
      setLoading(false)
      onStatusChange?.('idle')
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages" ref={scrollRef}>
        {messages.length === 0 && liveTranscript === null && (
          <div className="chat-empty">
            <p>Ask me anything about what I've seen.</p>
            <p className="chat-empty-hint">"Where are my keys?" or "What's on the table?"</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Live transcription bubble — grows as the user speaks */}
        {liveTranscript !== null && (
          <div className="message user">
            <div className="bubble live-bubble">
              {liveTranscript
                ? liveTranscript
                : <span className="live-placeholder">Listening...</span>}
              <span className="live-cursor" />
            </div>
          </div>
        )}

        {loading && (
          <div className="message assistant">
            <div className="bubble thinking">
              <span className="dot-pulse" />
              <span className="dot-pulse d2" />
              <span className="dot-pulse d3" />
            </div>
          </div>
        )}
      </div>
      <ChatInput onSend={handleSend} disabled={loading} />
    </div>
  )
}
