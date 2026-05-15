import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Zap, Trash2, ChevronDown, Loader2, AlertCircle, Check, History } from 'lucide-react'
import { RadialBarChart, RadialBar, PolarGrid, PolarRadiusAxis, Label } from 'recharts'
import PlatformLogo from '../shared/PlatformLogo'
import { usePostureScore } from '../../api/posture'
import { useSyncConnector, useDeleteConnector, useTestConnector, useSetConnectorSchedule } from '../../api/connectors'
import { PLATFORMS, formatRelative } from '../../lib/utils'
import type { Connector } from '../../api/types'

const INTERVAL_OPTIONS: { label: string; value: number | null }[] = [
  { label: 'Off',      value: null },
  { label: '15 min',   value: 15 },
  { label: '30 min',   value: 30 },
  { label: '1 hour',   value: 60 },
  { label: '3 hours',  value: 180 },
  { label: '6 hours',  value: 360 },
  { label: '12 hours', value: 720 },
  { label: '24 hours', value: 1440 },
]

export default function ConnectorPostureCard({ connector }: Readonly<{ connector: Connector }>) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const scheduleRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  const sync = useSyncConnector()
  const del = useDeleteConnector()
  const test = useTestConnector()
  const schedule = useSetConnectorSchedule()

  const { data: postureData } = usePostureScore(connector.id)
  const score = postureData?.score ?? 0
  const connected = connector.connection_ok === true
  const hasPosture = !!postureData

  const platform = PLATFORMS[connector.platform_name]
  const hasSchedule = !!connector.sync_interval_minutes
  const scheduleLabel = INTERVAL_OPTIONS.find((o) => o.value === connector.sync_interval_minutes)?.label ?? ''

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (scheduleRef.current && !scheduleRef.current.contains(e.target as Node)) {
        setScheduleOpen(false)
      }
    }
    if (scheduleOpen) document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [scheduleOpen])

  async function handleSync() {
    await sync.mutateAsync(connector.id).catch(() => undefined)
  }

  async function handleTest() {
    setTestResult(null)
    try {
      const res = await test.mutateAsync(connector.id)
      setTestResult({ ok: res.ok, msg: res.ok ? 'Connection OK' : (res.error ?? 'Failed') })
    } catch (err) {
      setTestResult({ ok: false, msg: err instanceof Error ? err.message : 'Failed' })
    }
    setTimeout(() => setTestResult(null), 4000)
  }

  async function handleDelete() {
    await del.mutateAsync(connector.id).catch(() => setConfirmDelete(false))
  }

  const barColor = !connected ? 'var(--border-strong)'
    : score >= 80 ? 'var(--ok)'
    : score >= 50 ? 'var(--sev-medium)'
    : 'var(--sev-critical)'

  const scoreAngle = connected && hasPosture ? Math.round((score / 100) * 250) : 1
  const chartData = [{ value: connected && hasPosture ? score : 0 }]

  const dotClass = connector.connection_ok === true ? 'status-dot ok'
    : connector.connection_ok === false ? 'status-dot err'
    : 'status-dot'

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16,
      padding: '20px', display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ position: 'relative', flexShrink: 0 }}>
          <PlatformLogo platform={connector.platform_name} />
          <span className={dotClass} style={{ position: 'absolute', bottom: -1, right: -1 }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontWeight: 600, fontSize: '0.9375rem', color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {connector.display_name}
          </p>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 1 }}>
            {platform?.label ?? connector.platform_name}
            {connector.last_sync_at && ` · ${formatRelative(connector.last_sync_at)}`}
            {hasSchedule && (
              <span style={{ color: 'var(--accent)', marginLeft: 4 }}>↻ {scheduleLabel}</span>
            )}
          </p>
        </div>
      </div>

      {/* Radial chart */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
        <RadialBarChart
          width={200} height={200}
          startAngle={0} endAngle={scoreAngle}
          innerRadius={68} outerRadius={90}
          data={chartData}
        >
          <PolarGrid gridType="circle" radialLines={false} stroke="none" polarRadius={[90, 68]} />
          <RadialBar
            dataKey="value"
            cornerRadius={10}
            fill={barColor}
            background={{ fill: 'var(--border)' }}
          />
          <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
            <Label
              content={({ viewBox }) => {
                if (viewBox && 'cx' in viewBox && 'cy' in viewBox) {
                  const cx = viewBox.cx as number
                  const cy = viewBox.cy as number
                  return (
                    <text textAnchor="middle" dominantBaseline="middle">
                      <tspan
                        x={cx} y={cy - 4}
                        style={{ fill: connected && hasPosture ? barColor : 'var(--text-muted)', fontSize: '2rem', fontWeight: 700 }}
                      >
                        {connected && hasPosture ? score : '–'}
                      </tspan>
                      <tspan
                        x={cx} y={cy + 22}
                        style={{ fill: 'var(--text-muted)', fontSize: '0.6875rem' }}
                      >
                        {connected && hasPosture ? 'Posture' : connected ? 'Loading…' : 'Not synced'}
                      </tspan>
                    </text>
                  )
                }
                return null
              }}
            />
          </PolarRadiusAxis>
        </RadialBarChart>
      </div>

      {/* Error banner */}
      {connector.last_sync_error && !testResult && (
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 6,
          padding: '8px 10px', borderRadius: 8,
          background: 'color-mix(in oklch, var(--sev-critical) 8%, transparent)',
        }}>
          <AlertCircle size={12} style={{ color: 'var(--sev-critical)', flexShrink: 0, marginTop: 1 }} />
          <span style={{ fontSize: '0.6875rem', color: 'var(--sev-critical)', fontFamily: 'monospace', wordBreak: 'break-all' }}>
            {connector.last_sync_error.slice(0, 120)}
          </span>
        </div>
      )}
      {testResult && (
        <p style={{ fontSize: '0.75rem', fontWeight: 500, textAlign: 'center', color: testResult.ok ? 'var(--ok)' : 'var(--sev-critical)' }}>
          {testResult.msg}
        </p>
      )}
      {sync.isError && !testResult && (
        <p style={{ fontSize: '0.75rem', color: 'var(--sev-critical)', textAlign: 'center' }}>Sync failed</p>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
        {confirmDelete ? (
          <>
            <span style={{ flex: 1, fontSize: '0.75rem', color: 'var(--text-muted)', alignSelf: 'center' }}>Delete?</span>
            <button onClick={() => setConfirmDelete(false)} className="btn-sm">Cancel</button>
            <button
              onClick={handleDelete}
              disabled={del.isPending}
              className="btn-sm"
              style={{ color: 'var(--sev-critical)', borderColor: 'color-mix(in oklch, var(--sev-critical) 30%, transparent)' }}
            >
              {del.isPending && <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} />}
              Delete
            </button>
          </>
        ) : (
          <>
            {/* Sync + schedule split button */}
            <div ref={scheduleRef} style={{ position: 'relative', display: 'inline-flex', flex: 1 }}>
              <button
                onClick={handleSync}
                disabled={sync.isPending}
                className="btn-sm"
                style={{ flex: 1, borderRadius: '8px 0 0 8px', borderRight: 'none', paddingRight: 8, justifyContent: 'center' }}
              >
                {sync.isPending
                  ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
                  : <RefreshCw size={13} />}
                Sync
              </button>
              <button
                onClick={() => setScheduleOpen((o) => !o)}
                disabled={schedule.isPending}
                className="btn-sm"
                title="Auto-sync schedule"
                style={{
                  borderRadius: '0 8px 8px 0',
                  paddingLeft: 5, paddingRight: 6,
                  borderLeft: '1px solid var(--border-strong)',
                  color: hasSchedule ? 'var(--accent)' : undefined,
                }}
              >
                <ChevronDown size={11} />
              </button>

              {scheduleOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 50,
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 10, boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
                  minWidth: 165, overflow: 'hidden',
                }}>
                  <div style={{ padding: '8px 12px 4px', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Auto-sync interval
                  </div>
                  {INTERVAL_OPTIONS.map((o) => {
                    const active = connector.sync_interval_minutes === o.value
                    return (
                      <button
                        key={String(o.value)}
                        onClick={() => { schedule.mutate({ id: connector.id, minutes: o.value }); setScheduleOpen(false) }}
                        style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          width: '100%', padding: '7px 12px', background: 'none', border: 'none',
                          cursor: 'pointer', fontSize: '0.8125rem', textAlign: 'left',
                          color: active ? 'var(--accent)' : 'var(--text)', fontWeight: active ? 600 : 400,
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)' }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = 'none' }}
                      >
                        {o.value ? `Every ${o.label}` : 'Off'}
                        {active && <Check size={12} style={{ color: 'var(--accent)' }} />}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <button onClick={handleTest} disabled={test.isPending} className="btn-sm" title="Test connection">
              {test.isPending ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap size={13} />}
              Test
            </button>
            <button onClick={() => navigate(`/connectors/${connector.id}`)} className="btn-sm" title="Scan history" style={{ padding: '6px 8px' }}>
              <History size={13} />
            </button>
            <button onClick={() => setConfirmDelete(true)} className="btn-sm" title="Delete" style={{ padding: '6px 8px' }}>
              <Trash2 size={13} />
            </button>
          </>
        )}
      </div>
    </div>
  )
}
