import { useState } from 'react'
import { usePipelines } from '@/hooks/usePipelines'
import PipelineCard from '@/components/PipelineCard'
import NewPipelineModal from '@/components/NewPipelineModal'

export default function PipelineList() {
  const { data: pipelines, isLoading, error } = usePipelines()
  const [modalOpen, setModalOpen] = useState(false)

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((n) => (
          <div key={n} className="rounded-lg border border-gray-800 bg-gray-900 p-4 h-24 animate-pulse" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-red-400 text-sm">
        Failed to load pipelines: {error.message}
      </div>
    )
  }

  return (
    <>
      <NewPipelineModal open={modalOpen} onClose={() => setModalOpen(false)} />

      <div>
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-semibold text-white">Pipelines</h1>
          <button
            onClick={() => setModalOpen(true)}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-500"
          >
            New Pipeline
          </button>
        </div>

        {(!pipelines || pipelines.length === 0) ? (
          <p className="text-gray-500 text-sm">No pipelines yet.</p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
            {pipelines.map((pipeline) => (
              <PipelineCard key={pipeline.id} pipeline={pipeline} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
