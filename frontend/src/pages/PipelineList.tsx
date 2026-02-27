import { usePipelines } from '@/hooks/usePipelines'
import PipelineCard from '@/components/PipelineCard'

export default function PipelineList() {
  const { data: pipelines, isLoading, error } = usePipelines()

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((n) => (
          <div key={n} className="rounded-lg border border-gray-800 bg-gray-900 p-4 h-24 animate-pulse" />
        ))}
      </div>
    )
  }

  if (error instanceof Error) {
    return (
      <div className="text-red-400 text-sm">
        Failed to load pipelines: {error.message}
      </div>
    )
  }

  if (!pipelines || pipelines.length === 0) {
    return (
      <p className="text-gray-500 text-sm">No pipelines yet. Start one via the API.</p>
    )
  }

  return (
    <div>
      <h1 className="text-lg font-semibold text-white mb-4">Pipelines</h1>
      <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
        {pipelines.map((pipeline) => (
          <PipelineCard key={pipeline.id} pipeline={pipeline} />
        ))}
      </div>
    </div>
  )
}
