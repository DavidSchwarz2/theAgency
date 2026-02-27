import { useState } from 'react'
import AgentFormModal from '@/components/AgentFormModal'
import { useAgentMutations, useAgents } from '@/hooks/useAgents'
import type { AgentProfileResponse, AgentWriteRequest } from '@/types/api'

export default function AgentsPage() {
  const { data: agents, isLoading, error } = useAgents()
  const { create, update, remove } = useAgentMutations()
  const [modalAgent, setModalAgent] = useState<AgentProfileResponse | null | 'new'>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)

  function handleSubmit(req: AgentWriteRequest) {
    if (modalAgent === 'new') {
      create.mutate(req, { onSuccess: () => setModalAgent(null) })
    } else if (modalAgent) {
      update.mutate({ name: modalAgent.name, req }, { onSuccess: () => setModalAgent(null) })
    }
  }

  const mutationError =
    (create.error instanceof Error ? create.error.message : null) ??
    (update.error instanceof Error ? update.error.message : null)

  const isPending = create.isPending || update.isPending

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-white font-semibold text-lg">Agents</h1>
        <button
          className="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white text-xs"
          onClick={() => setModalAgent('new')}
        >
          New Agent
        </button>
      </div>

      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}
      {error instanceof Error && <p className="text-red-400 text-sm">{error.message}</p>}

      <div className="space-y-3">
        {agents?.map((agent) => (
          <article key={agent.name} className="rounded-lg border border-gray-800 bg-gray-900 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="font-semibold text-white text-sm">{agent.name}</h3>
                <p className="text-gray-400 text-xs mt-0.5">{agent.description}</p>
                <p className="text-gray-600 text-xs mt-1">
                  agent: <span className="text-gray-500">{agent.opencode_agent}</span>
                  {agent.default_model && (
                    <> · model: <span className="text-gray-500">{agent.default_model}</span></>
                  )}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                  onClick={() => setModalAgent(agent)}
                >
                  Edit
                </button>
                {deleteConfirm === agent.name ? (
                  <span className="flex items-center gap-1">
                    <button
                      className="px-2 py-1 rounded bg-red-700 hover:bg-red-600 text-white text-xs disabled:opacity-50"
                      disabled={remove.isPending}
                      onClick={() => remove.mutate(agent.name, { onSuccess: () => setDeleteConfirm(null) })}
                    >
                      Confirm
                    </button>
                    <button
                      className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                      onClick={() => setDeleteConfirm(null)}
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    className="px-2 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs"
                    onClick={() => setDeleteConfirm(agent.name)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
            {remove.error instanceof Error && deleteConfirm === agent.name && (
              <p className="text-red-400 text-xs mt-1">{remove.error.message}</p>
            )}
          </article>
        ))}
      </div>

      {modalAgent !== null && (
        <AgentFormModal
          agent={modalAgent === 'new' ? undefined : modalAgent}
          onClose={() => setModalAgent(null)}
          onSubmit={handleSubmit}
          isPending={isPending}
          error={mutationError}
        />
      )}
    </div>
  )
}
