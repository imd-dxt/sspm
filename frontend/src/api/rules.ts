import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { get } from './client'
import type { Rule, ScanRun } from './types'

export function useRules(): UseQueryResult<Rule[]> {
  return useQuery({
    queryKey: ['rules'],
    queryFn: () => get<Rule[]>('/rules/'),
    staleTime: 5 * 60 * 1000, // 5 min — rules change rarely
  })
}

export function useScanRuns(): UseQueryResult<ScanRun[]> {
  return useQuery({
    queryKey: ['scan-runs'],
    queryFn: () => get<ScanRun[]>('/scan_runs/'),
    refetchInterval: 30_000,
  })
}

export function useScanRunsByConnector(connectorId: string): UseQueryResult<ScanRun[]> {
  return useQuery({
    queryKey: ['scan-runs', connectorId],
    queryFn: () => get<ScanRun[]>(`/scan_runs/?connector_id=${connectorId}`),
    enabled: !!connectorId,
    refetchInterval: 30_000,
  })
}
