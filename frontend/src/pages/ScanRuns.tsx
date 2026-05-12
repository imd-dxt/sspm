import { useState } from 'react'
import { CheckCircle, XCircle, Clock, Loader2, Activity, ChevronDown, ChevronRight } from 'lucide-react'
import { useScanRuns } from '../api/rules'
import { useConnectors } from '../api/connectors'
import { formatAbsolute, formatRelative } from '../lib/utils'
import type { ScanRun } from '../api/types'

function statusIcon(status: string) {
  if (status === 'completed') return <CheckCircle size={14} style={{ color: 'var(--ok)' }} />
  if (status === 'failed') return <XCircle size={14} style={{ color: 'var(--sev-high)' }} />
  if (status === 'running') return <Loader2 size={14} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
  return <Clock size={14} style={{ color: 'var(--text-muted)' }} />
}

function statusPillStyle(status: string): React.CSSProperties {
  if (status === 'completed') return { color: 'var(--ok)', background: 'color-mix(in oklch, var(--ok) 12%, transparent)' }
  if (status === 'failed') return { color: 'var(--sev-high)', background: 'color-mix(in oklch, var(--sev-high) 12%, transparent)' }
  if (status === 'running') return { color: 'var(--accent)', background: 'color-mix(in oklch, var(--accent) 12%, transparent)' }
  return { color: 'var(--text-muted)', background: 'color-mix(in oklch, var(--text-muted) 12%, transparent)' }
}

function connOkColor(ok: boolean | null): string {
  if (ok === true) return 'var(--ok)'
  if (ok === false) return 'var(--sev-high)'
  return 'var(--text-muted)'
}

function connOkLabel(ok: boolean | null): string {
  if (ok === true) return 'OK'
  if (ok === false) return 'Failed'
  return '—'
}

function durationMs(run: ScanRun): string {
  if (!run.started_at || !run.completed_at) return '—'
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 60_000)}m`
}

function ScanRunRow({ run, connectorName }: Readonly<{ run: ScanRun; connectorName: string }>) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div>
      <button
        onClick={() => setExpanded((e) => !e)}
        style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
      >
        <div className="data-row" style={{ gridTemplateColumns: '28px 1fr 160px 100px 70px 70px 70px 20px' }}>
          {statusIcon(run.status)}
          <span style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {run.id}
          </span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{connectorName}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{formatRelative(run.started_at)}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{durationMs(run)}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{run.records_fetched}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{run.findings_count}</span>
          {expanded ? <ChevronDown size={13} style={{ color: 'var(--text-muted)' }} /> : <ChevronRight size={13} style={{ color: 'var(--text-muted)' }} />}
        </div>
      </button>

      {expanded && (
        <div style={{ padding: '16px 20px', background: 'var(--surface-2)', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
            <div>
              <p className="label">Status</p>
              <span
                style={{
                  display: 'inline-flex', alignItems: 'center', borderRadius: 20,
                  padding: '2px 9px', fontSize: '0.75rem', fontWeight: 600, textTransform: 'capitalize',
                  ...statusPillStyle(run.status),
                }}
              >
                {run.status}
              </span>
            </div>
            <div>
              <p className="label">Started</p>
              <p style={{ fontSize: '0.875rem', color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{formatAbsolute(run.started_at)}</p>
            </div>
            <div>
              <p className="label">Completed</p>
              <p style={{ fontSize: '0.875rem', color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{formatAbsolute(run.completed_at)}</p>
            </div>
            <div>
              <p className="label">Connection</p>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: connOkColor(run.connection_ok) }}>
                {connOkLabel(run.connection_ok)}
              </p>
            </div>
          </div>
          {run.errors.length > 0 && (
            <div>
              <p className="label">Errors ({run.errors.length})</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {run.errors.map((err) => (
                  <pre key={JSON.stringify(err)} className="code-block" style={{ color: 'var(--sev-critical)' }}>
                    {JSON.stringify(err, null, 2)}
                  </pre>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ScanRuns() {
  const { data, isLoading, isError, refetch } = useScanRuns()
  const { data: connectors } = useConnectors()

  const connectorMap = new Map(connectors?.map((c) => [c.id, c.display_name]) ?? [])

  const sorted = data
    ? [...data].sort((a, b) => {
        const at = a.started_at ? new Date(a.started_at).getTime() : 0
        const bt = b.started_at ? new Date(b.started_at).getTime() : 0
        return bt - at
      })
    : []

  const completed = sorted.filter((r) => r.status === 'completed').length
  const failed = sorted.filter((r) => r.status === 'failed').length
  const running = sorted.filter((r) => r.status === 'running').length

  return (
    <div>
      {/* Stat strip */}
      {!isLoading && sorted.length > 0 && (
        <div className="stat-strip" style={{ marginBottom: 20 }}>
          <div className="stat-cell">
            <span className="stat-value">{sorted.length}</span>
            <span className="stat-label">Total</span>
          </div>
          <div className="stat-cell">
            <span className="stat-value" style={{ color: 'var(--ok)' }}>{completed}</span>
            <span className="stat-label">Completed</span>
          </div>
          <div className="stat-cell">
            <span className="stat-value" style={{ color: failed > 0 ? 'var(--sev-high)' : 'var(--text-muted)' }}>{failed}</span>
            <span className="stat-label">Failed</span>
          </div>
          <div className="stat-cell" style={{ borderRight: 'none' }}>
            <span className="stat-value" style={{ color: running > 0 ? 'var(--accent)' : 'var(--text-muted)' }}>{running}</span>
            <span className="stat-label">Running</span>
          </div>
        </div>
      )}

      {isError && (
        <div style={{
          borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12,
          background: 'color-mix(in oklch, var(--sev-critical) 10%, transparent)',
          border: '1px solid color-mix(in oklch, var(--sev-critical) 25%, transparent)',
          marginBottom: 14,
        }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', flex: 1 }}>Failed to load scan runs.</p>
          <button onClick={() => refetch()} style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>Retry</button>
        </div>
      )}

      {isLoading && (
        <div className="data-table">
          {[1, 2, 3].map((i) => (
            <div key={i} className="data-row" style={{ gridTemplateColumns: '28px 1fr 160px 100px 70px 70px 70px 20px' }}>
              <div className="skeleton" style={{ width: 14, height: 14, borderRadius: '50%' }} />
              <div className="skeleton" style={{ height: 14 }} />
              <div className="skeleton" style={{ height: 14, width: 100 }} />
              <div className="skeleton" style={{ height: 14, width: 70 }} />
              <div /><div /><div /><div />
            </div>
          ))}
        </div>
      )}

      {!isLoading && !isError && sorted.length === 0 && (
        <div className="empty-state">
          <Activity size={28} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
          <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>No scan runs yet</p>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Go to Connectors and click "Sync" to trigger a scan.
          </p>
        </div>
      )}

      {!isLoading && !isError && sorted.length > 0 && (
        <div className="data-table">
          <div className="table-head" style={{ display: 'grid', gridTemplateColumns: '28px 1fr 160px 100px 70px 70px 70px 20px' }}>
            <span />
            <span>Run ID</span>
            <span>Connector</span>
            <span>Started</span>
            <span>Duration</span>
            <span>Records</span>
            <span>Findings</span>
            <span />
          </div>
          {sorted.map((run) => (
            <ScanRunRow
              key={run.id}
              run={run}
              connectorName={connectorMap.get(run.connector_id) ?? run.connector_id}
            />
          ))}
        </div>
      )}
    </div>
  )
}
