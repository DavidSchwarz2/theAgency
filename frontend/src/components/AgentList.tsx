import { useAgents } from '@/hooks/useAgents'

export function AgentList() {
  const { agents, error, loading } = useAgents()

  if (loading) {
    return <p className="text-gray-600 text-sm">Loading agents...</p>
  }

  if (error) {
    return <p className="text-red-400 text-sm">Error loading agents: {error}</p>
  }

  if (agents.length === 0) {
    return <p className="text-gray-600 text-sm">No agents configured.</p>
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {agents.map((agent) => (
        <div
          key={agent.name}
          className="rounded-lg border border-gray-800 bg-gray-900 p-4 hover:border-gray-700 transition-colors"
        >
          <h3 className="text-sm font-semibold text-gray-200">{agent.name}</h3>
          <p className="mt-1 text-xs text-gray-500">{agent.opencode_agent}</p>
          <p className="mt-2 text-xs text-gray-400 leading-relaxed">{agent.description}</p>
        </div>
      ))}
    </div>
  )
}
