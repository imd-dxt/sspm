import { useState, useMemo } from 'react'
import { Filter, Activity } from 'lucide-react'
import PlatformLogo from '../components/shared/PlatformLogo'
import { useActivityLogs, useActivityLogSummary } from '../api/activityLogs'
import { platformLabel, formatRelative } from '../lib/utils'
import type { ActivityLogEntry } from '../api/types'

const PLATFORM_OPTIONS = ['', 'github', 'entraid', 'jira', 'salesforce']
const SEVERITY_OPTIONS = ['all', 'critical', 'warning', 'info'] as const
type SevFilter = typeof SEVERITY_OPTIONS[number]

function deriveSeverity(action: string): 'critical' | 'warning' | 'info' {
  if (/delete|block|fail|unknown|attack|blocked|breach/i.test(action)) return 'critical'
  if (/add|assign|grant|invite|personal access token|elevat|admin/i.test(action)) return 'warning'
  return 'info'
}

const SEV_COLOR: Record<string, string> = {
  critical: 'var(--sev-critical)',
  warning:  'var(--sev-medium)',
  info:     'var(--ok)',
}
const SEV_BG: Record<string, string> = {
  critical: 'color-mix(in oklch, var(--sev-critical) 12%, transparent)',
  warning:  'color-mix(in oklch, var(--sev-medium) 12%, transparent)',
  info:     'color-mix(in oklch, var(--ok) 12%, transparent)',
}

const MOCK_LOGS: ActivityLogEntry[] = [
  { id: -1, connector_id: 'demo', platform: 'entraid',  actor: 'john.doe@acme.com',      action: 'User invited to organization',            resource: 'finance-team',                    timestamp: '2026-05-11T08:15:00Z' },
  { id: -2, connector_id: 'demo', platform: 'github',   actor: 'jane.smith@acme.com',     action: 'Admin role granted to external user',     resource: 'repos/acme-payments/api',         timestamp: '2026-05-11T07:45:00Z' },
  { id: -3, connector_id: 'demo', platform: 'entraid',  actor: null,                      action: 'MFA enforcement policy deleted',           resource: 'CA-Policy-01',                    timestamp: '2026-05-10T22:30:00Z' },
  { id: -4, connector_id: 'demo', platform: 'github',   actor: 'contractor@external.io',  action: 'Personal access token created',           resource: 'repos/acme-payments/core',        timestamp: '2026-05-10T18:00:00Z' },
  { id: -5, connector_id: 'demo', platform: 'entraid',  actor: 'admin@acme.com',           action: 'Global administrator role assigned',       resource: 'user:bob.wilson@acme.com',        timestamp: '2026-05-10T14:20:00Z' },
  { id: -6, connector_id: 'demo', platform: 'github',   actor: 'devops@acme.com',          action: 'Repository access added for service account', resource: 'repos/acme-payments/infra',  timestamp: '2026-05-10T11:10:00Z' },
  { id: -7, connector_id: 'demo', platform: 'entraid',  actor: 'security@acme.com',        action: 'Conditional access policy updated',        resource: 'CA-Policy-MFA',                   timestamp: '2026-05-09T16:45:00Z' },
  { id: -8, connector_id: 'demo', platform: 'github',   actor: 'alice@acme.com',           action: 'Branch protection rule removed',           resource: 'repos/acme-payments/api:main',    timestamp: '2026-05-09T09:00:00Z' },
]

export default function ActivityLogs() {
  const [platform, setPlatform] = useState('')
  const [sevFilter, setSevFilter] = useState<SevFilter>('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [limit, setLimit] = useState(100)

  const { data: summary } = useActivityLogSummary()
  const { data: rawLogs, isLoading } = useActivityLogs(
    platform || undefined,
    undefined, // actor
    undefined, // action
    undefined,
    limit,
  )

  const isMock = !rawLogs || rawLogs.length === 0
  let baseLogs: ActivityLogEntry[]
  if (isLoading) {
    baseLogs = []
  } else if (isMock) {
    baseLogs = MOCK_LOGS
  } else {
    baseLogs = rawLogs
  }

  const filtered = useMemo(() => {
    let list = baseLogs
    if (sevFilter !== 'all') list = list.filter((e) => deriveSeverity(e.action) === sevFilter)
    if (dateFrom) {
      const from = new Date(dateFrom)
      list = list.filter((e) => new Date(e.timestamp) >= from)
    }
    if (dateTo) {
      const to = new Date(dateTo + 'T23:59:59Z')
      list = list.filter((e) => new Date(e.timestamp) <= to)
    }
    if (platform && isMock) list = list.filter((e) => e.platform === platform)
    return list
  }, [baseLogs, sevFilter, dateFrom, dateTo, platform, isMock])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>Activity Logs</h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          Audit trail from your connected SaaS platforms.
        </p>
      </div>

      {/* Summary KPIs */}
      {summary && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 20px', minWidth: 120 }}>
            <p style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent)', fontVariantNumeric: 'tabular-nums' }}>{summary.total.toLocaleString()}</p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3, fontWeight: 500 }}>Total events</p>
          </div>
          {Object.entries(summary.by_platform).map(([plat, count]) => (
            <div key={plat} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 10, minWidth: 120 }}>
              <PlatformLogo platform={plat} size={22} />
              <div>
                <p style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{count}</p>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>{platformLabel(plat)}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', padding: '12px 16px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}>
        <Filter size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />

        {/* Platform pills */}
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {PLATFORM_OPTIONS.map((p) => (
            <button
              key={p || 'all'}
              onClick={() => setPlatform(p)}
              style={{
                padding: '4px 12px', borderRadius: 20, fontSize: '0.75rem', fontWeight: 500, cursor: 'pointer',
                border: `1px solid ${platform === p ? 'var(--accent)' : 'var(--border)'}`,
                background: platform === p ? 'color-mix(in oklch, var(--accent) 10%, var(--surface))' : 'var(--surface)',
                color: platform === p ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              {p ? platformLabel(p) : 'All'}
            </button>
          ))}
        </div>

        <div style={{ width: 1, height: 20, background: 'var(--border)', flexShrink: 0 }} />

        {/* Severity pills */}
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {SEVERITY_OPTIONS.map((s) => {
            const active = sevFilter === s
            const color = s === 'all' ? 'var(--accent)' : SEV_COLOR[s]
            const bg = s === 'all'
              ? 'color-mix(in oklch, var(--accent) 10%, var(--surface))'
              : SEV_BG[s]
            return (
              <button
                key={s}
                onClick={() => setSevFilter(s)}
                style={{
                  padding: '4px 12px', borderRadius: 20, fontSize: '0.75rem', fontWeight: 500, cursor: 'pointer',
                  border: `1px solid ${active ? color : 'var(--border)'}`,
                  background: active ? bg : 'var(--surface)',
                  color: active ? color : 'var(--text-muted)',
                }}
              >
                {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            )
          })}
        </div>

        {/* Date range */}
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            style={{ padding: '5px 8px', fontSize: '0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 7, color: 'var(--text)' }}
          />
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>→</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            style={{ padding: '5px 8px', fontSize: '0.75rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 7, color: 'var(--text)' }}
          />
        </div>
      </div>

      {/* Timeline feed */}
      {isLoading && <TimelineSkeleton />}
      {!isLoading && filtered.length === 0 && <EmptyLogs />}
      {!isLoading && filtered.length > 0 && (
        <>
          {isMock && (
            <div style={{ padding: '8px 14px', background: 'color-mix(in oklch, var(--sev-medium) 8%, transparent)', border: '1px solid color-mix(in oklch, var(--sev-medium) 20%, transparent)', borderRadius: 8, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Demo data — connect a SaaS platform to see real activity logs.
            </div>
          )}
          <div style={{ position: 'relative' }}>
            {/* Vertical timeline line */}
            <div style={{ position: 'absolute', left: 18, top: 8, bottom: 8, width: 2, background: 'var(--border)', borderRadius: 1 }} />
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {filtered.map((entry, idx) => {
                const sev = deriveSeverity(entry.action)
                return (
                  <TimelineEntry
                    key={entry.id}
                    entry={entry}
                    sev={sev}
                    color={SEV_COLOR[sev]}
                    bg={SEV_BG[sev]}
                    isLast={idx === filtered.length - 1}
                  />
                )
              })}
            </div>
          </div>
          {!isMock && filtered.length >= limit && (
            <div style={{ textAlign: 'center', paddingLeft: 38 }}>
              <button
                onClick={() => setLimit((l) => l + 100)}
                style={{ padding: '8px 24px', borderRadius: 8, fontSize: '0.8125rem', fontWeight: 500, border: '1.5px solid var(--border)', background: 'var(--surface)', color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                Load more
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function TimelineEntry({ entry, sev, color, bg, isLast }: Readonly<{
  entry: ActivityLogEntry
  sev: string
  color: string
  bg: string
  isLast: boolean
}>) {
  return (
    <div style={{ display: 'flex', gap: 14, paddingBottom: isLast ? 0 : 2 }}>
      {/* Dot */}
      <div style={{ flexShrink: 0, width: 38, display: 'flex', justifyContent: 'center', paddingTop: 14 }}>
        <div style={{
          width: 12, height: 12, borderRadius: '50%',
          background: color, border: '2px solid var(--surface)',
          zIndex: 1, position: 'relative', flexShrink: 0,
          boxShadow: `0 0 0 2px ${bg}`,
        }} />
      </div>

      {/* Card */}
      <div
        style={{
          flex: 1, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: '10px 14px', marginBottom: 8,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, flex: 1, minWidth: 0 }}>
            <PlatformLogo platform={entry.platform} size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <div style={{ minWidth: 0 }}>
              <p style={{ fontSize: '0.875rem', color: 'var(--text)', fontWeight: 500, lineHeight: 1.3 }}>
                {entry.action}
              </p>
              <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                {entry.actor && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                    {entry.actor}
                  </span>
                )}
                {entry.actor && entry.resource && (
                  <span style={{ color: 'var(--border-strong)', fontSize: '0.75rem' }}>→</span>
                )}
                {entry.resource && (
                  <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 280 }}>
                    {entry.resource}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
            <span style={{
              padding: '2px 8px', borderRadius: 20, fontSize: '0.6875rem', fontWeight: 600,
              background: bg, color,
            }}>
              {sev}
            </span>
            <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
              {formatRelative(entry.timestamp)}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

const SKELETON_ROWS = [
  { id: 'sk-a', delay: '0ms' },
  { id: 'sk-b', delay: '80ms' },
  { id: 'sk-c', delay: '160ms' },
  { id: 'sk-d', delay: '240ms' },
  { id: 'sk-e', delay: '320ms' },
]

function TimelineSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: 38 }}>
      {SKELETON_ROWS.map((row) => (
        <div
          key={row.id}
          style={{ height: 68, borderRadius: 10, background: 'var(--surface-2)', animation: 'pulse 1.5s ease-in-out infinite', animationDelay: row.delay }}
        />
      ))}
    </div>
  )
}

function EmptyLogs() {
  return (
    <div style={{ padding: '48px 24px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, textAlign: 'center', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <Activity size={32} style={{ opacity: 0.3 }} />
      <p style={{ fontSize: '0.875rem' }}>No activity logs match your filters.</p>
      <p style={{ fontSize: '0.75rem' }}>Logs are fetched from connected platforms during sync.</p>
    </div>
  )
}
