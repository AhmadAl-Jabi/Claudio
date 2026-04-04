import { useState } from 'react'
import LiveFeed from './components/LiveFeed'
import ChatPanel from './components/ChatPanel'
import TopBar from './components/TopBar'
import './App.css'

function App() {
  const [feedActive, setFeedActive] = useState(false)
  const [status, setStatus] = useState('idle')

  return (
    <div className="app">
      <LiveFeed onFeedChange={setFeedActive} />
      <div className="overlay-ui">
        <TopBar feedActive={feedActive} status={status} />
        <div className="overlay-body">
          <ChatPanel onStatusChange={setStatus} />
        </div>
      </div>
    </div>
  )
}

export default App
