/**
 * Shared TypeScript types matching the backend REST API schema.
 */

export type PipelineStatus = 'pending' | 'running' | 'waiting_for_approval' | 'done' | 'failed'
export type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

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
  model: string | null
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
  branch: string | null
  working_dir: string | null
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

/** A single step in a custom pipeline composition (Issue #16). */
export interface CustomStepInput {
  type: 'agent' | 'approval'
  agent?: string
  model?: string
}

export interface PipelineCreateRequest {
  /** Named template — mutually exclusive with custom_steps. */
  template?: string
  /** Custom step list — mutually exclusive with template. */
  custom_steps?: CustomStepInput[]
  title: string
  prompt: string
  branch?: string
  step_models?: Record<string, string>
  working_dir?: string
  /** GitHub issue enrichment (Issue #13). */
  github_issue_repo?: string
  github_issue_number?: number
}

export interface PipelineTemplateStepResponse {
  type: string
  agent?: string
  description: string
}

export interface PipelineTemplateResponse {
  name: string
  description: string
  steps: PipelineTemplateStepResponse[]
}

/** Returned by GET /registry/agents. */
export interface AgentProfileResponse {
  name: string
  description: string
  opencode_agent: string
  default_model: string | null
}

/** Request body for POST /registry/agents and PUT /registry/agents/{name}. */
export interface AgentWriteRequest {
  name: string
  description: string
  opencode_agent: string
  default_model: string | null
  system_prompt_additions: string
}

/** Request body for POST /registry/pipelines and PUT /registry/pipelines/{name}. */
export interface AgentStepWrite {
  type: 'agent'
  agent: string
  description: string
  model: string | null
}

export interface ApprovalStepWrite {
  type: 'approval'
  description: string
}

export type PipelineStepWrite = AgentStepWrite | ApprovalStepWrite

export interface PipelineWriteRequest {
  name: string
  description: string
  steps: PipelineStepWrite[]
}

/** Returned by GET /registry/github-issue (Issue #13). */
export interface GitHubIssueResponse {
  number: number
  title: string
  body: string | null
  labels: string[]
}

/** Returned by GET /health/opencode. */
export interface OpenCodeStatusResponse {
  available: boolean
}

/** Returned by POST /health/opencode/start. */
export interface OpenCodeStartResponse {
  available: boolean
  started: boolean
}

/** Returned by GET /fs/browse. */
export interface FsEntry {
  name: string
  path: string
  is_dir: boolean
}

export interface FsBrowseResponse {
  path: string
  parent: string | null
  entries: FsEntry[]
}
