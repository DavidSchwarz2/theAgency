/**
 * Shared TypeScript types matching the backend REST API schema.
 */

export type PipelineStatus = 'pending' | 'running' | 'waiting_for_approval' | 'done' | 'failed'
export type StepStatus = 'pending' | 'running' | 'done' | 'failed'

export interface HandoffResponse {
  id: number
  content_md: string
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface Step {
  id: number
  agent_name: string
  order_index: number
  status: StepStatus
  started_at: string | null
  finished_at: string | null
  latest_handoff: HandoffResponse | null
}

/** Returned by GET /pipelines (list) — no steps field. */
export interface Pipeline {
  id: number
  title: string
  template: string
  status: PipelineStatus
  created_at: string
  updated_at: string
}

/** Returned by GET /pipelines/{id} (detail) — includes steps. */
export interface PipelineDetail extends Pipeline {
  steps: Step[]
}

export interface AuditEvent {
  id: number
  pipeline_id: number
  step_id: number | null
  event_type: string
  payload: Record<string, unknown> | null
  created_at: string
}

export interface AuditQueryParams {
  pipeline_id?: number
  event_type?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}
