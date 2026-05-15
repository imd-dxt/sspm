import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { get } from './client'

export interface ComplianceControl {
  id: string
  name: string
  status: 'pass' | 'fail' | 'unknown'
  open_findings: number
  total_findings: number
  rules: string[]
}

export interface ComplianceStandard {
  id: string
  name: string
  description: string
  score: number
  total_controls: number
  passing_controls: number
  failing_controls: number
  unknown_controls: number
  controls: ComplianceControl[]
}

export interface ComplianceReport {
  standards: ComplianceStandard[]
  overall_score: number
  last_updated: string | null
}

export function useComplianceReport(): UseQueryResult<ComplianceReport> {
  return useQuery({
    queryKey: ['compliance'],
    queryFn: () => get<ComplianceReport>('/compliance/'),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}
