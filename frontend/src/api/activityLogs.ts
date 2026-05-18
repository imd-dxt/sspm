import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { get, post } from './client'
import type { ActivityLogEntry, ActivityLogSummary, PostureScore, PrioritizedActionsResponse } from './types'

export function useActivityLogs(
  platform?: string,
  actor?: string,
  action?: string,
  connectorId?: string,
  limit = 100,
  offset = 0,
): UseQueryResult<ActivityLogEntry[]> {
  return useQuery({
    queryKey: ['activity-logs', platform, actor, action, connectorId, limit, offset],
    queryFn: () =>
      get<ActivityLogEntry[]>('/activity-logs/', {
        platform,
        actor,
        action,
        connector_id: connectorId,
        limit,
        offset,
      }),
    refetchInterval: 60_000,
  })
}

export function useActivityLogSummary(): UseQueryResult<ActivityLogSummary> {
  return useQuery({
    queryKey: ['activity-logs-summary'],
    queryFn: () => get<ActivityLogSummary>('/activity-logs/summary'),
    refetchInterval: 60_000,
  })
}

export function usePostureScore(
  platform?: string,
  connectorId?: string,
): UseQueryResult<PostureScore> {
  return useQuery({
    queryKey: ['posture-score', platform, connectorId],
    queryFn: () =>
      get<PostureScore>('/posture/score', {
        platform,
        connector_id: connectorId,
      }),
    refetchInterval: 60_000,
  })
}

export function usePrioritizedActions(
  platform?: string,
  limit = 5,
): UseQueryResult<PrioritizedActionsResponse> {
  return useQuery({
    queryKey: ['prioritized-actions', platform, limit],
    queryFn: () =>
      post<PrioritizedActionsResponse>(`/posture/prioritized-actions`, undefined, {
        platform,
        limit,
      }),
    staleTime: 90_000,
    refetchInterval: 120_000,
  })
}
