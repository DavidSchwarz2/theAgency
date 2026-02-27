import { useEffect, useRef, useState } from 'react'

import { AgentList } from '@/components/AgentList'

type HeartbeatEvent = { type: string; ts: number }

function App() {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<HeartbeatEvent[]>([])
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const es = new EventSource('/api/events')
    esRef.current = es

    es.onopen = () => setConnected(true)
    es.onerror = () => setConnected(false)
    es.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data) as HeartbeatEvent
        setEvents((prev) => [payload, ...prev].slice(0, 20))
      } catch {
        // ignore malformed frames
      }
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, [])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 font-mono p-8">
      <header className="mb-8 flex items-center gap-4">
        <h1 className="text-2xl font-bold tracking-tight">theAgency</h1>
        <span
          className={`px-2 py-0.5 rounded text-xs font-semibold ${
            connected ? 'bg-green-800 text-green-200' : 'bg-red-900 text-red-300'
          }`}
        >
          {connected ? 'connected' : 'disconnected'}
        </span>
      </header>

      <section>
        <h2 className="text-sm uppercase tracking-widest text-gray-500 mb-3">Backend Events</h2>
        {events.length === 0 ? (
          <p className="text-gray-600 text-sm">Waiting for events…</p>
        ) : (
          <ul className="space-y-1">
            {events.map((ev, i) => (
              <li key={i} className="text-xs text-gray-400">
                <span className="text-gray-600 mr-2">{new Date(ev.ts * 1000).toLocaleTimeString()}</span>
                {ev.type}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-8">
        <h2 className="text-sm uppercase tracking-widest text-gray-500 mb-3">Agents</h2>
        <AgentList />
      </section>
    </div>
  )
}

export default App
