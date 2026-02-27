import { useState } from 'react'
import { useAuditEvents } from '@/hooks/useAuditEvents'
import type { AuditEvent, AuditQueryParams } from '@/types/api'

const PAGE_SIZE = 50

export default function AuditTrail() {
  const [filters, setFilters] = useState<AuditQueryParams>({ limit: PAGE_SIZE, offset: 0 })
  const [pipelineIdInput, setPipelineIdInput] = useState('')
  const [eventTypeInput, setEventTypeInput] = useState('')
  const [sinceInput, setSinceInput] = useState('')

  const { data: events, isLoading, error, refetch } = useAuditEvents(filters)

  const applyFilters = () => {
    const params: AuditQueryParams = { limit: PAGE_SIZE, offset: 0 }
    if (pipelineIdInput) {
      const parsed = Number(pipelineIdInput)
      if (Number.isInteger(parsed) && parsed > 0) params.pipeline_id = parsed
    }
    if (eventTypeInput) params.event_type = eventTypeInput
    if (sinceInput) params.since = new Date(sinceInput).toISOString().slice(0, 19)
    setFilters(params)
  }

  const loadMore = () => {
    setFilters((prev) => ({ ...prev, offset: (prev.offset ?? 0) + PAGE_SIZE }))
  }

  return (
    <div>
      <h1 className="text-lg font-semibold text-white mb-4">Audit Trail</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Pipeline ID</label>
          <input
            type="number"
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white w-28"
            value={pipelineIdInput}
            onChange={(e) => setPipelineIdInput(e.target.value)}
            placeholder="any"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Event type</label>
          <input
            type="text"
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white w-44"
            value={eventTypeInput}
            onChange={(e) => setEventTypeInput(e.target.value)}
            placeholder="e.g. handoff_created"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Since</label>
          <input
            type="datetime-local"
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-white"
            value={sinceInput}
            onChange={(e) => setSinceInput(e.target.value)}
          />
        </div>
        <button
          className="px-4 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white text-sm"
          onClick={applyFilters}
        >
          Filter
        </button>
        <button
          className="px-4 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-white text-sm"
          onClick={() => void refetch()}
        >
          Refresh
        </button>
      </div>

      {/* Table */}
      {isLoading && <p className="text-gray-500 text-sm">Loading…</p>}
      {error instanceof Error && (
        <p className="text-red-400 text-sm">Error: {error.message}</p>
      )}
      {!isLoading && events && events.length === 0 && (
        <p className="text-gray-500 text-sm">No audit events found.</p>
      )}
      {events && events.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500">
                  <th className="py-2 pr-4">ID</th>
                  <th className="py-2 pr-4">Pipeline</th>
                  <th className="py-2 pr-4">Step</th>
                  <th className="py-2 pr-4">Event type</th>
                  <th className="py-2 pr-4">Created at</th>
                  <th className="py-2">Payload</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <EventRow key={ev.id} event={ev} />
                ))}
              </tbody>
            </table>
          </div>
          {events.length === PAGE_SIZE && (
            <button
              className="mt-4 px-4 py-1.5 rounded bg-gray-700 hover:bg-gray-600 text-white text-sm"
              onClick={loadMore}
            >
              Next page
            </button>
          )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Single row with expandable payload
// ---------------------------------------------------------------------------

function EventRow({ event }: { event: AuditEvent }) {
  const [expanded, setExpanded] = useState(false)
  const payloadStr = event.payload ? JSON.stringify(event.payload) : ''
  const truncated = payloadStr.length > 60 ? `${payloadStr.slice(0, 60)}…` : payloadStr

  return (
    <tr className="border-b border-gray-900 hover:bg-gray-900 align-top">
      <td className="py-1.5 pr-4 text-gray-500">{event.id}</td>
      <td className="py-1.5 pr-4 text-gray-400">{event.pipeline_id}</td>
      <td className="py-1.5 pr-4 text-gray-400">{event.step_id ?? '—'}</td>
      <td className="py-1.5 pr-4 text-blue-300">{event.event_type}</td>
      <td className="py-1.5 pr-4 text-gray-400 whitespace-nowrap">
        {new Date(event.created_at).toLocaleString()}
      </td>
      <td className="py-1.5 text-gray-400">
        {payloadStr ? (
          <>
            <span>{expanded ? payloadStr : truncated}</span>
            {payloadStr.length > 60 && (
              <button
                className="ml-1 text-gray-600 hover:text-gray-400 underline"
                onClick={() => setExpanded((e) => !e)}
              >
                {expanded ? 'less' : 'more'}
              </button>
            )}
          </>
        ) : (
          <span className="text-gray-700">—</span>
        )}
      </td>
    </tr>
  )
}
