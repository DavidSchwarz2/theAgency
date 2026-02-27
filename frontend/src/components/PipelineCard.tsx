import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Pipeline, PipelineStatus, Step, StepStatus } from '@/types/api'
import { useApprovalMutation } from '@/hooks/useApprovalMutation'

// ---------------------------------------------------------------------------
// Status badge helpers
// ---------------------------------------------------------------------------

const PIPELINE_STATUS_CLASSES: Record<PipelineStatus, string> = {
  pending: 'bg-gray-600 text-gray-200',
  running: 'bg-blue-600 text-blue-100 animate-pulse',
  waiting_for_approval: 'bg-yellow-500 text-yellow-950 font-bold',
  done: 'bg-green-700 text-green-100',
  failed: 'bg-red-700 text-red-100',
}

const STEP_STATUS_CLASSES: Record<StepStatus, string> = {
  pending: 'bg-gray-700 text-gray-400',
  running: 'bg-blue-600 text-blue-100 animate-pulse',
  done: 'bg-green-700 text-green-200',
  failed: 'bg-red-700 text-red-200',
  skipped: 'bg-gray-700 text-gray-500',
}

function StatusBadge({ status }: { status: PipelineStatus }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs ${PIPELINE_STATUS_CLASSES[status]}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Step row with expandable handoff
// ---------------------------------------------------------------------------

function StepRow({ step }: { step: Step }) {
  const [expanded, setExpanded] = useState(step.status === 'running')
  const handoff = step.latest_handoff

  return (
    <div className="text-xs">
      <div className="flex items-center gap-2 py-0.5">
        <span className={`px-1.5 py-0.5 rounded ${STEP_STATUS_CLASSES[step.status]}`}>
          {step.status}
        </span>
        <span className="text-gray-300">{step.agent_name}</span>
        {handoff && (
          <button
            className="text-gray-500 hover:text-gray-300 underline ml-auto"
            onClick={() => setExpanded((e) => !e)}
          >
            {expanded ? 'hide handoff' : 'view handoff'}
          </button>
        )}
      </div>
      {expanded && handoff && (
        <div className="mt-1 ml-2 border-l-2 border-gray-700 pl-3">
          {handoff.metadata ? (
            <dl className="space-y-1">
              {Object.entries(handoff.metadata).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-gray-500 inline">{k}: </dt>
                  <dd className="text-gray-300 inline whitespace-pre-wrap">
                    {typeof v === 'string' ? v : JSON.stringify(v)}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <div className="prose prose-invert prose-xs max-w-none text-gray-300">
              <ReactMarkdown>{handoff.content_md}</ReactMarkdown>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Approval actions banner
// ---------------------------------------------------------------------------

function ApprovalBanner({ pipelineId }: { pipelineId: number }) {
  const { approve, reject } = useApprovalMutation(pipelineId)
  const [comment, setComment] = useState('')
  const isPending = approve.isPending || reject.isPending
  // Show only the error from the mutation that is currently (or was last) active.
  const error = approve.isPending || approve.isError ? approve.error : reject.error

  function handleApprove() {
    approve.mutate(comment, { onSuccess: () => setComment('') })
  }

  function handleReject() {
    reject.mutate(comment, { onSuccess: () => setComment('') })
  }

  return (
    <div className="mt-3 p-3 rounded bg-yellow-950 border border-yellow-700">
      <p className="text-yellow-300 text-xs font-semibold mb-2">Waiting for approval</p>
      <label className="block mb-2">
        <span className="text-yellow-400 text-xs">Optional comment</span>
        <textarea
          className="mt-1 block w-full rounded bg-yellow-900 border border-yellow-700 text-yellow-100 text-xs px-2 py-1 resize-none placeholder-yellow-700 focus:outline-none focus:border-yellow-500"
          rows={2}
          placeholder="Leave a note for the next agent step…"
          value={comment}
          disabled={isPending}
          onChange={(e) => setComment(e.target.value)}
        />
      </label>
      <div className="flex gap-2">
        <button
          className="px-3 py-1 rounded bg-green-700 hover:bg-green-600 text-white text-xs disabled:opacity-50"
          disabled={isPending}
          aria-label="Approve pipeline"
          onClick={handleApprove}
        >
          Approve
        </button>
        <button
          className="px-3 py-1 rounded bg-red-700 hover:bg-red-600 text-white text-xs disabled:opacity-50"
          disabled={isPending}
          aria-label="Reject pipeline"
          onClick={handleReject}
        >
          Reject
        </button>
      </div>
      {error instanceof Error && (
        <p className="text-red-400 text-xs mt-1">{error.message}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pipeline card
// ---------------------------------------------------------------------------

/** Props accept a Pipeline (from list endpoint) or a PipelineDetail (from detail endpoint).
 *  Steps are shown only when present, as the list endpoint omits them. */
export default function PipelineCard({ pipeline }: { pipeline: Pipeline & { steps?: Step[] } }) {
  const sortedSteps = [...(pipeline.steps ?? [])].sort((a, b) => a.order_index - b.order_index)

  return (
    <article className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="font-semibold text-white text-sm">{pipeline.title}</h3>
          <p className="text-gray-500 text-xs mt-0.5">{pipeline.template}</p>
        </div>
        <StatusBadge status={pipeline.status} />
      </div>

      {sortedSteps.length > 0 && (
        <div className="space-y-1 mb-3">
          {sortedSteps.map((step) => (
            <StepRow key={step.id} step={step} />
          ))}
        </div>
      )}

      {pipeline.status === 'waiting_for_approval' && (
        <ApprovalBanner pipelineId={pipeline.id} />
      )}

      <p className="text-gray-600 text-xs mt-2">
        #{pipeline.id} · {new Date(pipeline.created_at).toLocaleString()}
      </p>
    </article>
  )
}
