import { useEffect, useState } from 'react'

export type Agent = {
  name: string
  description: string
  opencode_agent: string
}

export function useAgents() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/registry/agents')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<Agent[]>
      })
      .then((data) => {
        setAgents(data)
        setError(null)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load agents')
      })
      .finally(() => setLoading(false))
  }, [])

  return { agents, error, loading }
}
