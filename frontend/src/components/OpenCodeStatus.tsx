import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchOpenCodeStatus, startOpenCode } from '@/api/client'

export default function OpenCodeStatus() {
  const queryClient = useQueryClient()
  const [startError, setStartError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['opencode-status'],
    queryFn: fetchOpenCodeStatus,
    refetchInterval: 10_000,
  })

  const { mutate: start, isPending: isStarting } = useMutation({
    mutationFn: startOpenCode,
    onSuccess: () => {
      setStartError(null)
      void queryClient.invalidateQueries({ queryKey: ['opencode-status'] })
    },
    onError: (err: Error) => {
      setStartError(err.message)
      void queryClient.invalidateQueries({ queryKey: ['opencode-status'] })
    },
  })

  if (isLoading) return null

  const available = data?.available ?? false

  return (
    <div className="flex items-center gap-2 px-6 py-1 text-xs border-b border-gray-900 bg-gray-950">
      <span className={`h-2 w-2 rounded-full ${available ? 'bg-green-500' : 'bg-yellow-500'}`} />
      <span className="text-gray-500">
        opencode: {available ? 'running' : 'not running'}
      </span>
      {!available && (
        <button
          onClick={() => start()}
          disabled={isStarting}
          className="ml-1 px-2 py-0.5 rounded text-xs font-mono bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed border border-gray-700"
        >
          {isStarting ? 'starting…' : 'start'}
        </button>
      )}
      {startError && (
        <span className="text-red-400 ml-1">failed to start</span>
      )}
    </div>
  )
}
