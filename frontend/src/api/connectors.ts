import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query'
import { get, post, del, patch } from './client'
import type {
  Connector,
  ConnectorCreate,
  ConnectorStatusResponse,
  ConnectorTestResponse,
  ScanRun,
} from './types'

export const CONNECTORS_KEY = ['connectors'] as const

export function useConnectors(): UseQueryResult<Connector[]> {
  return useQuery({
    queryKey: CONNECTORS_KEY,
    queryFn: () => get<Connector[]>('/connectors/'),
    refetchInterval: 30_000,
  })
}

export function useConnectorStatus(id: string): UseQueryResult<ConnectorStatusResponse> {
  return useQuery({
    queryKey: ['connector-status', id],
    queryFn: () => get<ConnectorStatusResponse>(`/connectors/${id}/status`),
    enabled: !!id,
    refetchInterval: 60_000,
  })
}

export function useTestConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => get<ConnectorTestResponse>(`/connectors/${id}/test`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTORS_KEY })
    },
  })
}

export function useSyncConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => post<ScanRun>(`/connectors/${id}/sync`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTORS_KEY })
      void queryClient.invalidateQueries({ queryKey: ['scan-runs'] })
      void queryClient.invalidateQueries({ queryKey: ['findings'] })
      void queryClient.invalidateQueries({ queryKey: ['findings-summary'] })
    },
  })
}

export function useCreateConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: ConnectorCreate) => post<Connector>('/connectors/', data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTORS_KEY })
    },
  })
}

export function useSetConnectorSchedule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, minutes }: { id: string; minutes: number | null }) =>
      patch<Connector>(`/connectors/${id}/schedule`, { sync_interval_minutes: minutes }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTORS_KEY })
    },
  })
}

export function useUpdateConnectorCredentials() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, credentials }: { id: string; credentials: Record<string, string> }) =>
      patch<Connector>(`/connectors/${id}/credentials`, { credentials }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTORS_KEY })
    },
  })
}

export function useDeleteConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del<void>(`/connectors/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CONNECTORS_KEY })
      void queryClient.invalidateQueries({ queryKey: ['findings'] })
      void queryClient.invalidateQueries({ queryKey: ['findings-summary'] })
    },
  })
}
