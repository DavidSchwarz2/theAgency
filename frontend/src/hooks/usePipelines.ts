import { useQuery } from '@tanstack/react-query'
import { fetchPipelines } from '@/api/client'
import type { Pipeline } from '@/types/api'

export function usePipelines() {
  return useQuery<Pipeline[]>({
    queryKey: ['pipelines'],
    queryFn: fetchPipelines,
    refetchInterval: 5_000,
  })
}
