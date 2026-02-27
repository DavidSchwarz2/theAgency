import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createAgent, deleteAgent, fetchAgents, updateAgent } from '@/api/client'
import type { AgentWriteRequest } from '@/types/api'

export function useAgents() {
  return useQuery({ queryKey: ['agents'], queryFn: fetchAgents })
}

export function useAgentMutations() {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['agents'] })

  const create = useMutation({
    mutationFn: (req: AgentWriteRequest) => createAgent(req),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ name, req }: { name: string; req: AgentWriteRequest }) => updateAgent(name, req),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (name: string) => deleteAgent(name),
    onSuccess: invalidate,
  })

  return { create, update, remove }
}
