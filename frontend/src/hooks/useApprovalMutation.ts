import { useMutation, useQueryClient } from '@tanstack/react-query'
import { approvePipeline, rejectPipeline } from '@/api/client'

export function useApprovalMutation(pipelineId: number) {
  const queryClient = useQueryClient()

  const onSuccess = () => {
    void queryClient.invalidateQueries({ queryKey: ['pipelines'] })
  }

  const approve = useMutation({
    mutationFn: (comment: string = '') => approvePipeline(pipelineId, comment),
    onSuccess,
  })

  const reject = useMutation({
    mutationFn: (comment: string = '') => rejectPipeline(pipelineId, comment),
    onSuccess,
  })

  return { approve, reject }
}
