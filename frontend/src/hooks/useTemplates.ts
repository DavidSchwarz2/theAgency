import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createTemplate, deleteTemplate, fetchPipelineTemplates, updateTemplate } from '@/api/client'
import type { PipelineWriteRequest } from '@/types/api'

export function useTemplates() {
  return useQuery({ queryKey: ['templates'], queryFn: fetchPipelineTemplates })
}

export function useTemplateMutations() {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['templates'] })

  const create = useMutation({
    mutationFn: (req: PipelineWriteRequest) => createTemplate(req),
    onSuccess: invalidate,
  })

  const update = useMutation({
    mutationFn: ({ name, req }: { name: string; req: PipelineWriteRequest }) => updateTemplate(name, req),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (name: string) => deleteTemplate(name),
    onSuccess: invalidate,
  })

  return { create, update, remove }
}
