import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  keepPreviousData,
} from '@tanstack/react-query'
import { get, put, post } from './client'
import type { Finding, FindingSummary, FindingsQuery, UpdateFindingStatus } from './types'

export function useFindings(query: FindingsQuery = {}): UseQueryResult<Finding[]> {
  return useQuery({
    queryKey: ['findings', query],
    queryFn: () =>
      get<Finding[]>('/findings/', {
        severity: query.severity,
        status: query.status,
        platform: query.platform,
        connector_id: query.connector_id,
        rule_id: query.rule_id,
        category: query.category,
        limit: query.limit ?? 100,
        offset: query.offset ?? 0,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  })
}

export function useFindingSummary(): UseQueryResult<FindingSummary> {
  return useQuery({
    queryKey: ['findings-summary'],
    queryFn: () => get<FindingSummary>('/findings/summary'),
    refetchInterval: 30_000,
  })
}

export function useFindingsByCategory(): UseQueryResult<Record<string, number>> {
  return useQuery({
    queryKey: ['findings-by-category'],
    queryFn: () => get<Record<string, number>>('/findings/by-category'),
    refetchInterval: 60_000,
  })
}

export function useCrossPlatformFindings(): UseQueryResult<Finding[]> {
  return useQuery({
    queryKey: ['findings-cross-platform'],
    queryFn: () => get<Finding[]>('/findings/cross-platform'),
    refetchInterval: 60_000,
  })
}

export function useUpdateFindingStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateFindingStatus }) =>
      put<Finding>(`/findings/${id}/status`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['findings'] })
      void queryClient.invalidateQueries({ queryKey: ['findings-summary'] })
      void queryClient.invalidateQueries({ queryKey: ['findings-cross-platform'] })
    },
  })
}

export function useAllFindings(platform?: string): UseQueryResult<Finding[]> {
  return useQuery({
    queryKey: ['findings-all', platform],
    queryFn: () =>
      get<Finding[]>('/findings/', {
        status: 'all',
        platform,
        limit: 500,
        offset: 0,
      }),
    refetchInterval: 60_000,
  })
}

export interface FindingTrendPoint {
  week: string
  open: number
  resolved: number
  false_positive: number
  accepted_risk: number
}

export function useFindingsTrend(
  platform?: string,
  days = 90,
): UseQueryResult<FindingTrendPoint[]> {
  return useQuery({
    queryKey: ['findings-trend', platform, days],
    queryFn: () =>
      get<FindingTrendPoint[]>('/findings/trend', { platform, days }),
    refetchInterval: 120_000,
  })
}

export function useAnalyzeFinding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<Finding>(`/findings/${id}/analyze`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['findings'] })
    },
  })
}

export function useRemediateFinding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<Finding>(`/findings/${id}/remediate`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['findings'] })
      void queryClient.invalidateQueries({ queryKey: ['prioritized-actions'] })
    },
  })
}

export interface CiaImpact {
  finding_id: number
  source: 'ollama' | 'static'
  confidentiality: string
  integrity: string
  availability: string
}

export function useCiaImpact() {
  return useMutation({
    mutationFn: (id: number) => post<CiaImpact>(`/findings/${id}/cia-impact`),
  })
}
