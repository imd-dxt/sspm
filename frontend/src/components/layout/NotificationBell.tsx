import { useState, useEffect, useRef, useMemo } from 'react'
import { Bell, CheckCircle2, AlertCircle, RefreshCw, X } from 'lucide-react'
import { useConnectors } from '../../api/connectors'
import { useScanRuns } from '../../api/rules'
import { formatRelative, platformLabel } from '../../lib/utils'

interface Notification {
  id: string
  kind: 'sync_ok' | 'sync_error' | 'conn_error'
  title: string
  detail: string
  time: string | null
  read: boolean
}

function buildNotifications(
  connectors: import('../../api/types').Connector[],
  scanRuns: import('../../api/types').ScanRun[],
): Notification[] {
  const notes: Notification[] = []

  // Connector-level errors
  for (const c of connectors) {
    if (c.connection_ok === false) {
      notes.push({
        id: `conn-err-${c.id}`,
        kind: 'conn_error',
        title: `${c.display_name} can't connect`,
        detail: c.last_sync_error
          ? c.last_sync_error.slice(0, 120)
          : 'Connection failed — check credentials',
        time: c.last_sync_at,
        read: false,
      })
    }
  }

  // Recent scan-run results (last 10, completed or failed)
  const recent = [...scanRuns]
    .filter((r) => r.completed_at || r.status === 'failed')
    .sort((a, b) => {
      const ta = a.completed_at ? new Date(a.completed_at).getTime() : 0
      const tb = b.completed_at ? new Date(b.completed_at).getTime() : 0
      return tb - ta
    })
    .slice(0, 10)

  for (const run of recent) {
    const connector = connectors.find((c) => c.id === run.connector_id)
    const name = connector ? connector.display_name : platformLabel(run.connector_id)

    if (run.status === 'failed' || (run.errors && run.errors.length > 0)) {
      notes.push({
        id: `scan-err-${run.id}`,
        kind: 'sync_error',
        title: `Sync failed — ${name}`,
        detail:
          run.errors?.[0]
            ? String(Object.values(run.errors[0])[0]).slice(0, 120)
            : 'Scan run ended with errors',
        time: run.completed_at,
        read: false,
      })
    } else if (run.status === 'completed') {
      notes.push({
        id: `scan-ok-${run.id}`,
        kind: 'sync_ok',
        title: `Sync completed — ${name}`,
        detail: `${run.records_fetched} records · ${run.findings_count} open finding${run.findings_count === 1 ? '' : 's'}`,
        time: run.completed_at,
        read: false,
      })
    }
  }

  return notes
}

const KIND_ICON = {
  sync_ok:    <CheckCircle2 size={14} style={{ color: 'var(--ok)', flexShrink: 0 }} />,
  sync_error: <AlertCircle  size={14} style={{ color: 'var(--sev-high)', flexShrink: 0 }} />,
  conn_error: <AlertCircle  size={14} style={{ color: 'var(--sev-critical)', flexShrink: 0 }} />,
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [readIds, setReadIds] = useState<Set<string>>(new Set())
  const panelRef = useRef<HTMLDivElement>(null)
  const btnRef  = useRef<HTMLButtonElement>(null)

  const { data: connectors = [] } = useConnectors()
  const { data: scanRuns   = [] } = useScanRuns()

  const notifications = useMemo(
    () => buildNotifications(connectors, scanRuns),
    [connectors, scanRuns],
  )

  const unread = notifications.filter((n) => !readIds.has(n.id))
  const unreadCount = unread.length

  // Close on outside click
  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        btnRef.current  && !btnRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  function markAllRead() {
    setReadIds(new Set(notifications.map((n) => n.id)))
  }

  function dismiss(id: string) {
    setReadIds((prev) => new Set([...prev, id]))
  }

  const displayed = notifications.filter((n) => !readIds.has(n.id))

  return (
    <div style={{ position: 'relative' }}>
      {/* Bell button */}
      <button
        ref={btnRef}
        onClick={() => setOpen((v) => !v)}
        className="btn-ghost"
        style={{ position: 'relative', padding: '6px 8px' }}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      >
        <Bell size={15} />
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute',
            top: 3,
            right: 3,
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: 'var(--sev-critical)',
            border: '1.5px solid var(--surface)',
          }} />
        )}
      </button>

      {/* Dropdown panel */}
      {open && (
        <div
          ref={panelRef}
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            width: 360,
            maxHeight: 460,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 12,
            boxShadow: '0 8px 32px rgba(0,0,0,0.14)',
            zIndex: 200,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: '1px solid var(--border)',
            flexShrink: 0,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Bell size={13} style={{ color: 'var(--text-muted)' }} />
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text)' }}>
                Notifications
              </span>
              {unreadCount > 0 && (
                <span style={{
                  background: 'var(--sev-critical)',
                  color: '#fff',
                  borderRadius: 10,
                  padding: '1px 6px',
                  fontSize: '0.625rem',
                  fontWeight: 700,
                }}>
                  {unreadCount}
                </span>
              )}
            </div>
            {displayed.length > 0 && (
              <button
                onClick={markAllRead}
                style={{
                  fontSize: '0.6875rem',
                  color: 'var(--accent)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {displayed.length === 0 ? (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                padding: '32px 20px',
                color: 'var(--text-muted)',
              }}>
                <RefreshCw size={22} style={{ opacity: 0.4 }} />
                <p style={{ fontSize: '0.8125rem' }}>All caught up</p>
                <p style={{ fontSize: '0.75rem', textAlign: 'center' }}>
                  Sync events and connector errors will appear here.
                </p>
              </div>
            ) : (
              displayed.map((n) => (
                <div
                  key={n.id}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                    padding: '11px 16px',
                    borderBottom: '1px solid var(--border)',
                    background: readIds.has(n.id) ? 'transparent' : 'color-mix(in oklch, var(--accent) 3%, transparent)',
                  }}
                >
                  <div style={{ marginTop: 2 }}>{KIND_ICON[n.kind]}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: n.kind === 'sync_ok' ? 'var(--text)' : n.kind === 'conn_error' ? 'var(--sev-critical)' : 'var(--sev-high)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {n.title}
                    </p>
                    <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2, lineHeight: 1.4 }}>
                      {n.detail}
                    </p>
                    {n.time && (
                      <p style={{ fontSize: '0.625rem', color: 'var(--text-muted)', marginTop: 3, opacity: 0.7 }}>
                        {formatRelative(n.time)}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => dismiss(n.id)}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      color: 'var(--text-muted)',
                      padding: 2,
                      flexShrink: 0,
                      marginTop: 1,
                    }}
                    aria-label="Dismiss"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
