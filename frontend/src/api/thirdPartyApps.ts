import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { get } from './client'

export interface ThirdPartyApp {
  id: string
  name: string
  resource_type: string
  platform: string
  connector_id: string | null
  connector_name: string | null
  findings_count: number
  open_findings: number
  highest_severity: string | null
  first_seen: string | null
  last_seen: string | null
}

export interface ThirdPartyAppSummary {
  total_apps: number
  risky_apps: number
  connectors_scanned: number
  apps: ThirdPartyApp[]
}

export function useThirdPartyApps(): UseQueryResult<ThirdPartyAppSummary> {
  return useQuery({
    queryKey: ['third-party-apps'],
    queryFn: () => get<ThirdPartyAppSummary>('/third-party-apps/'),
    staleTime: 60_000,
  })
}
