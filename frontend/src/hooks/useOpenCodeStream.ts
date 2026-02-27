import { useEffect, useState } from 'react'

const MAX_LINES = 200

/**
 * Opens an EventSource connection to /api/events while `active` is true.
 * Returns an array of raw JSON strings (one per non-heartbeat event),
 * capped at MAX_LINES. The array is cleared when `active` becomes false.
 */
export function useOpenCodeStream(active: boolean): string[] {
  const [lines, setLines] = useState<string[]>([])

  useEffect(() => {
    if (!active) {
      setLines([])
      return
    }

    const es = new EventSource('/api/events')

    es.onmessage = (e: MessageEvent<string>) => {
      try {
        const parsed: unknown = JSON.parse(e.data)
        if (typeof parsed === 'object' && parsed !== null && 'type' in parsed) {
          if ((parsed as { type: unknown }).type === 'heartbeat') return
        }
      } catch {
        // not JSON — still show it
      }
      setLines((prev) => {
        const next = [...prev, e.data]
        return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
      })
    }

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        es.close()
      }
      // CONNECTING state means auto-reconnect is in progress — no action needed
    }

    return () => {
      es.close()
    }
  }, [active])

  return lines
}
