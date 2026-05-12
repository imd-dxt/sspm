import { useState } from 'react'
import { RefreshCw, Trash2, Zap, Loader2, AlertCircle } from 'lucide-react'
import type { Connector } from '../../api/types'
import { useSyncConnector, useDeleteConnector, useTestConnector } from '../../api/connectors'
import { cn, formatRelative, PLATFORMS } from '../../lib/utils'

interface Props {
  connector: Connector
}

function StatusDot({ ok }: { ok: boolean | null }) {
  if (ok === true) {
    return (
      <span
        className="h-2.5 w-2.5 rounded-full flex-shrink-0 ring-2 ring-offset-1"
        style={{ background: 'var(--conn-ok)' }}
        aria-label="Connected"
      />
    )
  }
  if (ok === false) {
    return (
      <span
        className="h-2.5 w-2.5 rounded-full flex-shrink-0 ring-2 ring-offset-1"
        style={{ background: 'var(--conn-err)' }}
        aria-label="Connection failed"
      />
    )
  }
  return (
    <span
      className="h-2.5 w-2.5 rounded-full flex-shrink-0 bg-muted/40"
      aria-label="Never synced"
    />
  )
}

function PlatformAvatar({ name }: { name: string }) {
  const platform = PLATFORMS[name]
  const abbr = platform?.abbr ?? name.slice(0, 2).toUpperCase()
  return (
    <div
      className="flex h-10 w-10 items-center justify-center rounded-xl font-mono text-sm font-bold text-white flex-shrink-0"
      style={{ background: 'var(--accent)' }}
    >
      {abbr}
    </div>
  )
}

export default function ConnectorCard({ connector }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  const sync = useSyncConnector()
  const del = useDeleteConnector()
  const test = useTestConnector()

  const platform = PLATFORMS[connector.platform_name]
  const statusText =
    connector.connection_ok === true
      ? 'Connected'
      : connector.connection_ok === false
        ? 'Connection failed'
        : 'Never synced'

  async function handleSync() {
    try {
      await sync.mutateAsync(connector.id)
    } catch (_) {
      // error shown inline
    }
  }

  async function handleTest() {
    setTestResult(null)
    try {
      const result = await test.mutateAsync(connector.id)
      setTestResult({
        ok: result.ok,
        message: result.ok ? 'Connection successful' : (result.error ?? 'Connection failed'),
      })
      setTimeout(() => setTestResult(null), 4000)
    } catch (err) {
      setTestResult({
        ok: false,
        message: err instanceof Error ? err.message : 'Test failed',
      })
      setTimeout(() => setTestResult(null), 4000)
    }
  }

  async function handleDelete() {
    try {
      await del.mutateAsync(connector.id)
    } catch (_) {
      setConfirmDelete(false)
    }
  }

  return (
    <div className="card flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start gap-3">
        <PlatformAvatar name={connector.platform_name} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <StatusDot ok={connector.connection_ok} />
            <p className="text-sm font-semibold text-text truncate">{platform?.label ?? connector.platform_name}</p>
          </div>
          <p className="text-xs text-muted truncate">{connector.display_name}</p>
        </div>
      </div>

      {/* Status */}
      <div className="text-xs space-y-1">
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              'font-medium',
              connector.connection_ok === true
                ? 'text-conn-ok'
                : connector.connection_ok === false
                  ? 'text-conn-err'
                  : 'text-muted',
            )}
            style={{
              color:
                connector.connection_ok === true
                  ? 'var(--conn-ok)'
                  : connector.connection_ok === false
                    ? 'var(--conn-err)'
                    : undefined,
            }}
          >
            {statusText}
          </span>
        </div>
        <p className="text-muted tabular-nums">
          Last sync:{' '}
          <span className="text-text">{formatRelative(connector.last_sync_at)}</span>
        </p>
      </div>

      {/* Error block */}
      {connector.last_sync_error && (
        <div className="flex items-start gap-2 rounded-lg bg-sev-critical/10 p-2">
          <AlertCircle size={12} className="mt-0.5 flex-shrink-0 text-sev-critical" style={{ color: 'var(--sev-critical)' }} />
          <p className="font-mono text-[10px] text-sev-critical break-all leading-relaxed" style={{ color: 'var(--sev-critical)' }}>
            {connector.last_sync_error}
          </p>
        </div>
      )}

      {/* Test result feedback */}
      {testResult && (
        <div
          className={cn(
            'flex items-center gap-2 rounded-lg px-2.5 py-2 text-xs font-medium',
            testResult.ok
              ? 'bg-sev-ok/10 text-sev-ok'
              : 'bg-sev-critical/10 text-sev-critical',
          )}
          style={{
            color: testResult.ok ? 'var(--conn-ok)' : 'var(--conn-err)',
            background: testResult.ok ? 'color-mix(in srgb, var(--conn-ok) 12%, transparent)' : 'color-mix(in srgb, var(--conn-err) 12%, transparent)',
          }}
        >
          {testResult.message}
        </div>
      )}

      {/* Sync/test errors */}
      {sync.isError && (
        <p className="text-xs text-sev-critical" style={{ color: 'var(--sev-critical)' }}>
          Sync failed:{' '}
          {sync.error instanceof Error ? sync.error.message : 'Unknown error'}
        </p>
      )}

      {/* Actions */}
      {!confirmDelete ? (
        <div className="flex items-center gap-2 pt-1 border-t border-border">
          <button
            onClick={handleSync}
            disabled={sync.isPending}
            className="btn-ghost flex-1 justify-center text-xs"
            title="Sync now"
          >
            {sync.isPending ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RefreshCw size={13} />
            )}
            Sync
          </button>
          <button
            onClick={handleTest}
            disabled={test.isPending}
            className="btn-ghost flex-1 justify-center text-xs"
            title="Test connection"
          >
            {test.isPending ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Zap size={13} />
            )}
            Test
          </button>
          <button
            onClick={() => setConfirmDelete(true)}
            className="btn-danger p-2"
            title="Delete connector"
          >
            <Trash2 size={13} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 pt-1 border-t border-border">
          <p className="flex-1 text-xs text-muted">Delete this connector?</p>
          <button
            onClick={() => setConfirmDelete(false)}
            className="btn-ghost text-xs"
          >
            Cancel
          </button>
          <button
            onClick={handleDelete}
            disabled={del.isPending}
            className="inline-flex items-center gap-1 rounded-lg bg-sev-critical px-3 py-1.5 text-xs font-medium text-white transition-colors"
            style={{ background: 'var(--sev-critical)' }}
          >
            {del.isPending && <Loader2 size={12} className="animate-spin" />}
            Delete
          </button>
        </div>
      )}
    </div>
  )
}
