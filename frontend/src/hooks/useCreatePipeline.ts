import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createPipeline } from '@/api/client'
import type { Pipeline, PipelineCreateRequest } from '@/types/api'

export function useCreatePipeline() {
  const queryClient = useQueryClient()

  return useMutation<Pipeline, Error, PipelineCreateRequest>({
    mutationFn: createPipeline,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pipelines'] })
    },
  })
}
