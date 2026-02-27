/**
 * Typed HTTP client. All paths go through the Vite dev proxy:
 * /api/* → http://localhost:8000/* (strips /api prefix).
 */

import type { AuditEvent, AuditQueryParams, Pipeline, PipelineCreateRequest, PipelineDetail, PipelineTemplateResponse } from '@/types/api'

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const hasBody = options?.body !== undefined
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`HTTP ${response.status}: ${text}`)
  }
  return response.json() as Promise<T>
}

export function fetchPipelines(): Promise<Pipeline[]> {
  return apiFetch<Pipeline[]>('/pipelines')
}

export function fetchPipeline(id: number): Promise<PipelineDetail> {
  return apiFetch<PipelineDetail>(`/pipelines/${id}`)
}

export function approvePipeline(id: number, comment = ''): Promise<Pipeline> {
  return apiFetch<Pipeline>(`/pipelines/${id}/approve`, {
    method: 'POST',
    body: JSON.stringify({ comment }),
  })
}

export function rejectPipeline(id: number, comment = ''): Promise<Pipeline> {
  return apiFetch<Pipeline>(`/pipelines/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ comment }),
  })
}

export function fetchAuditEvents(params: AuditQueryParams = {}): Promise<AuditEvent[]> {
  const searchParams = new URLSearchParams()
  if (params.pipeline_id !== undefined) searchParams.set('pipeline_id', String(params.pipeline_id))
  if (params.event_type !== undefined) searchParams.set('event_type', params.event_type)
  if (params.since) searchParams.set('since', params.since)
  if (params.until) searchParams.set('until', params.until)
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit))
  if (params.offset !== undefined) searchParams.set('offset', String(params.offset))
  const qs = searchParams.toString()
  return apiFetch<AuditEvent[]>(`/audit${qs ? `?${qs}` : ''}`)
}

export function createPipeline(req: PipelineCreateRequest): Promise<Pipeline> {
  return apiFetch<Pipeline>('/pipelines', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export function fetchPipelineTemplates(): Promise<PipelineTemplateResponse[]> {
  return apiFetch<PipelineTemplateResponse[]>('/registry/pipelines')
}