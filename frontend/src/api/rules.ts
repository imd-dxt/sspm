import { useQuery, useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { get, post, patch, del } from './client'
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

// ── Custom Policies ──────────────────────────────────────────────────────────

export interface CustomPolicyCreate {
  name:               string
  platform:           'github' | 'jira' | 'salesforce' | 'entraid' | 'cross-platform'
  severity:           'critical' | 'high' | 'medium' | 'low' | 'info'
  category:           string
  description:        string
  remediation:        string
  referentials:       string[]   // CIS | SOC2 | ISO27001 | NIST-CSF
  compliance_mapping: { [framework: string]: string }[]
  detection_query:    string
}

export function useCreateCustomPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: CustomPolicyCreate) => post<Rule>('/rules/custom', data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })
}

export function useUpdateCustomPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CustomPolicyCreate & { is_active: boolean }> }) =>
      patch<Rule>(`/rules/custom/${id}`, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })
}

export function useDeleteCustomPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del<void>(`/rules/custom/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rules'] })
    },
  })
}
