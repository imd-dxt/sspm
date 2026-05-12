import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { get } from './client'
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
