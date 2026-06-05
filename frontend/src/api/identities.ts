import { useQuery, useMutation, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { get, put } from './client'
import type {
  IdentityPlatform,
  IdentitySummary,
  IdentityUser,
  IdentityResourceRow,
  FindingByResource,
  IdentityGraph,
} from './types'

export function useIdentityPlatforms(): UseQueryResult<IdentityPlatform[]> {
  return useQuery({
    queryKey: ['identity-platforms'],
    queryFn: () => get<IdentityPlatform[]>('/identities/platforms'),
    refetchInterval: 60_000,
  })
}

export function useIdentitySummary(
  platform: string,
  connectorId?: string,
): UseQueryResult<IdentitySummary> {
  return useQuery({
    queryKey: ['identity-summary', platform, connectorId],
    queryFn: () =>
      get<IdentitySummary>('/identities/summary', {
        platform,
        connector_id: connectorId,
      }),
    enabled: !!platform,
    refetchInterval: 60_000,
  })
}

export function useIdentityUsers(
  platform: string,
  connectorId?: string,
  limit = 100,
  offset = 0,
): UseQueryResult<IdentityUser[]> {
  return useQuery({
    queryKey: ['identity-users', platform, connectorId, limit, offset],
    queryFn: () =>
      get<IdentityUser[]>('/identities/users', {
        platform,
        connector_id: connectorId,
        limit,
        offset,
      }),
    enabled: !!platform,
    refetchInterval: 60_000,
  })
}

export function useIdentityResources(
  platform: string,
  connectorId?: string,
  limit = 100,
  offset = 0,
): UseQueryResult<IdentityResourceRow[]> {
  return useQuery({
    queryKey: ['identity-resources', platform, connectorId, limit, offset],
    queryFn: () =>
      get<IdentityResourceRow[]>('/identities/resources', {
        platform,
        connector_id: connectorId,
        limit,
        offset,
      }),
    enabled: !!platform,
    refetchInterval: 60_000,
  })
}

export function useFindingsByResource(
  platform: string,
  connectorId?: string,
  limit = 25,
): UseQueryResult<FindingByResource[]> {
  return useQuery({
    queryKey: ['identity-findings-by-resource', platform, connectorId, limit],
    queryFn: () =>
      get<FindingByResource[]>('/identities/findings-by-resource', {
        platform,
        connector_id: connectorId,
        limit,
      }),
    enabled: !!platform,
    refetchInterval: 60_000,
  })
}

export interface IdentitySettings {
  internal_email_domains: string[]
  inactive_user_days:     number
  extra_admin_roles:      string[]
  flag_external_users:    boolean
  alert_on_new_admin:     boolean
}

export const IDENTITY_SETTINGS_KEY = ['identity-settings'] as const

export function useIdentitySettings(): UseQueryResult<IdentitySettings> {
  return useQuery({
    queryKey: IDENTITY_SETTINGS_KEY,
    queryFn: () => get<IdentitySettings>('/identities/settings'),
  })
}

export function useUpdateIdentitySettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: IdentitySettings) =>
      put<IdentitySettings>('/identities/settings', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: IDENTITY_SETTINGS_KEY })
      // External-user counts depend on the new domain list
      void queryClient.invalidateQueries({ queryKey: ['identity-summary'] })
      void queryClient.invalidateQueries({ queryKey: ['identity-users'] })
    },
  })
}

export interface CrossPlatformUser {
  email: string
  display_name: string
  platforms: string[]
  platform_count: number
  usernames: { platform: string; username: string }[]
  is_admin: boolean
  open_findings: number
  critical: number
  high: number
  medium: number
  low: number
  risk_score: number
}

export function useCrossPlatformUsers(limit = 50): UseQueryResult<CrossPlatformUser[]> {
  return useQuery({
    queryKey: ['identity-cross-platform-users', limit],
    queryFn: () => get<CrossPlatformUser[]>('/identities/cross-platform-users', { limit }),
    refetchInterval: 60_000,
  })
}

export function useIdentityGraph(
  platform: string,
  connectorId?: string,
): UseQueryResult<IdentityGraph> {
  return useQuery({
    queryKey: ['identity-graph', platform, connectorId],
    queryFn: () =>
      get<IdentityGraph>('/identities/graph', {
        platform,
        connector_id: connectorId,
      }),
    enabled: !!platform,
    refetchInterval: 120_000,
  })
}
