import { useQuery } from '@tanstack/react-query'
import { fetchAuditEvents } from '@/api/client'
import type { AuditEvent, AuditQueryParams } from '@/types/api'

export function useAuditEvents(params: AuditQueryParams = {}) {
  return useQuery<AuditEvent[]>({
    queryKey: ['audit', params],
    queryFn: () => fetchAuditEvents(params),
  })
}
