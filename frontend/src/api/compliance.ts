import { useMutation, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { get, post } from './client'

// ── Legacy overview types (GET /) ─────────────────────────────────────────────

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
  not_applicable_controls: number
  controls: ComplianceControl[]
}

export interface ComplianceReport {
  standards: ComplianceStandard[]
  overall_score: number
  last_updated: string | null
}

export function useComplianceReport(): UseQueryResult<ComplianceReport> {
  return useQuery({
    queryKey: ['compliance', 'overview'],
    queryFn: () => get<ComplianceReport>('/compliance/'),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

// ── Scores ────────────────────────────────────────────────────────────────────

export interface PlatformScore {
  platform: string
  framework: string
  framework_name: string
  score: number
  total_rules: number
  passed_rules: number
  failed_rules: number
}

export function useComplianceScores(): UseQueryResult<PlatformScore[]> {
  return useQuery({
    queryKey: ['compliance', 'scores'],
    queryFn: () => get<PlatformScore[]>('/compliance/scores'),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useComplianceScoresByPlatform(platform: string): UseQueryResult<PlatformScore[]> {
  return useQuery({
    queryKey: ['compliance', 'scores', platform],
    queryFn: () => get<PlatformScore[]>(`/compliance/scores/${platform}`),
    enabled: !!platform,
    staleTime: 60_000,
  })
}

// ── Trends ────────────────────────────────────────────────────────────────────

export interface TrendPoint {
  snapshot_date: string
  platform: string
  framework: string
  score: number
}

export function useComplianceTrends(
  platform?: string,
  framework?: string,
  days = 30,
): UseQueryResult<TrendPoint[]> {
  return useQuery({
    queryKey: ['compliance', 'trends', platform, framework, days],
    queryFn: () =>
      get<TrendPoint[]>('/compliance/trends', {
        ...(platform && { platform }),
        ...(framework && { framework }),
        days,
      }),
    staleTime: 60_000,
  })
}

// ── Reports ───────────────────────────────────────────────────────────────────

export interface StoredReport {
  id: number
  platform: string
  framework: string
  score: number
  total_rules: number
  passed_rules: number
  failed_rules: number
  ai_narrative: string | null
  created_at: string
}

export function useComplianceReports(): UseQueryResult<StoredReport[]> {
  return useQuery({
    queryKey: ['compliance', 'reports'],
    queryFn: () => get<StoredReport[]>('/compliance/reports'),
    staleTime: 30_000,
  })
}

export function useGenerateReport() {
  return useMutation({
    mutationFn: (data: { platform: string; framework: string; with_ai_narrative?: boolean }) =>
      post<StoredReport>('/compliance/report', data),
  })
}

// ── AI Assistant ──────────────────────────────────────────────────────────────

export interface AskResponse {
  answer: string
  source: 'ollama' | 'static'
}

export function useAskCompliance() {
  return useMutation({
    mutationFn: (data: { question: string; platform?: string; framework?: string }) =>
      post<AskResponse>('/compliance/ask', data),
  })
}

// ── AI Fix ────────────────────────────────────────────────────────────────────

export interface FixResponse {
  finding_id: number
  suggestion: string
  source: 'ollama' | 'static'
}

export function useGetAIFix() {
  return useMutation({
    mutationFn: (findingId: number) => post<FixResponse>(`/compliance/fix/${findingId}`),
  })
}
