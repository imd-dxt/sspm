import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import type { PostureScore } from './types'

export function usePostureScore(connectorId?: string) {
  return useQuery({
    queryKey: ['posture-score', connectorId],
    queryFn: () =>
      get<PostureScore>('/posture/score', connectorId ? { connector_id: connectorId } : {}),
    refetchInterval: 60_000,
  })
}
