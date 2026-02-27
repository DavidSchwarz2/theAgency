import { useEffect, useRef, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import NavBar from '@/components/NavBar'
import OpenCodeStatus from '@/components/OpenCodeStatus'
import PipelineList from '@/pages/PipelineList'
import AuditTrail from '@/pages/AuditTrail'

function App() {
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const queryClient = useQueryClient()

  useEffect(() => {
    const es = new EventSource('/api/events')
    esRef.current = es

    es.onopen = () => setConnected(true)
    es.onerror = () => {
      // EventSource fires onerror on every reconnect attempt; only mark
      // disconnected when the connection is permanently closed.
      if (es.readyState === EventSource.CLOSED) setConnected(false)
    }
    es.onmessage = () => {
      // Invalidate pipeline list on any SSE event so cards stay current.
      void queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    }

    return () => {
      es.close()
      setConnected(false)
    }
  }, [queryClient])

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 font-mono flex flex-col">
      <NavBar />
      <div className="flex items-center gap-2 px-6 py-1 text-xs border-b border-gray-900 bg-gray-950">
        <span
          className={`h-2 w-2 rounded-full ${connected ? 'bg-green-500' : 'bg-red-600'}`}
        />
        <span className="text-gray-500">{connected ? 'live' : 'reconnecting…'}</span>
      </div>
      <OpenCodeStatus />
      <main className="flex-1 p-6">
        <Routes>
          <Route path="/" element={<PipelineList />} />
          <Route path="/audit" element={<AuditTrail />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
