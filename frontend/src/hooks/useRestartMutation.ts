import { useMutation, useQueryClient } from '@tanstack/react-query'
import { restartPipeline } from '@/api/client'

export function useRestartMutation(pipelineId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => restartPipeline(pipelineId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['pipelines'] }),
  })
}
