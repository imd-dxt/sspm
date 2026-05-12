import { useState, useMemo } from 'react'
import { Search, Filter, X, ChevronRight, TrendingUp } from 'lucide-react'
import {
  PieChart, Pie, Cell, Tooltip as RTooltip, ResponsiveContainer,
} from 'recharts'
import { useFindings, useFindingSummary } from '../api/findings'
import { useConnectors } from '../api/connectors'
import FindingDrawer from '../components/findings/FindingDrawer'
import SeverityBadge from '../components/findings/SeverityBadge'
import type { Finding } from '../api/types'
import { formatRelative, platformLabel, statusLabel } from '../lib/utils'

// ── Shared chart-card shell (shadcn/ui style) ────────────────────────────────

function ChartCard({ title, description, footer, children }: Readonly<{
  title: string
  description: string
  footer?: React.ReactNode
  children: React.ReactNode
}>) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 14,
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* header */}
      <div style={{ padding: '16px 20px 0', textAlign: 'center' }}>
        <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)', marginBottom: 3 }}>{title}</p>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{description}</p>
      </div>
      {/* content */}
      <div style={{ flex: 1, padding: '4px 20px 0' }}>
        {children}
      </div>
      {/* footer */}
      {footer && (
        <div style={{
          padding: '12px 20px 16px',
          borderTop: '1px solid var(--border)',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          alignItems: 'center',
          fontSize: '0.75rem',
        }}>
          {footer}
        </div>
      )}
    </div>
  )
}

// ── Severity Donut (pie, no separator) ───────────────────────────────────────

const SEV_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high:     '#f97316',
  medium:   '#eab308',
  low:      '#3b82f6',
}

function SeverityDonut() {
  const { data: summary } = useFindingSummary()
  const sev = summary?.open_by_severity

  const chartData = useMemo(() => {
    if (!sev) return []
    return [
      { name: 'Critical', value: sev.critical, fill: SEV_COLORS.critical },
      { name: 'High',     value: sev.high,     fill: SEV_COLORS.high },
      { name: 'Medium',   value: sev.medium,   fill: SEV_COLORS.medium },
      { name: 'Low',      value: sev.low,      fill: SEV_COLORS.low },
    ].filter((d) => d.value > 0)
  }, [sev])

  const total = summary?.total ?? 0

  const footer = (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, color: 'var(--text)' }}>
        <TrendingUp size={14} />
        {total} open finding{total === 1 ? '' : 's'} total
      </div>
      <span style={{ color: 'var(--text-muted)' }}>Breakdown by severity level</span>
    </>
  )

  return (
    <ChartCard title="Findings by Severity" description="Open findings only" footer={footer}>
      {chartData.length === 0 ? (
        <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          No open findings
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              outerRadius={88}
              dataKey="value"
              nameKey="name"
              stroke="0"
            >
              {chartData.map((entry) => (
                <Cell key={entry.name} fill={entry.fill} />
              ))}
            </Pie>
            <RTooltip
              cursor={false}
              formatter={(v: number, name: string) => [`${v}`, name]}
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: '0.75rem' }}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

// ── Status Distribution Pie ───────────────────────────────────────────────────

const STATUS_COLORS = {
  open:           '#f97316',
  resolved:       '#22c55e',
  false_positive: '#94a3b8',
  accepted_risk:  '#eab308',
}

const STATUS_LEGEND = [
  { key: 'open',           label: 'Open',           color: STATUS_COLORS.open },
  { key: 'resolved',       label: 'Resolved',       color: STATUS_COLORS.resolved },
  { key: 'accepted_risk',  label: 'Accepted risk',  color: STATUS_COLORS.accepted_risk },
  { key: 'false_positive', label: 'False positive', color: STATUS_COLORS.false_positive },
]

function StatusDonut() {
  const { data: summary } = useFindingSummary()

  const chartData = useMemo(() => {
    if (!summary?.by_status) return []
    return STATUS_LEGEND
      .map(({ key, label, color }) => ({
        name: label,
        value: summary.by_status[key] ?? 0,
        fill: color,
      }))
      .filter((d) => d.value > 0)
  }, [summary])

  const byStatus = summary?.by_status ?? {}
  const total = Object.values(byStatus).reduce((s: number, v: number) => s + v, 0)

  const footer = (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, color: 'var(--text)' }}>
        <TrendingUp size={14} />
        {total} finding{total === 1 ? '' : 's'} across all statuses
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
        {STATUS_LEGEND.map((s) => (
          <span key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)' }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, display: 'inline-block', flexShrink: 0 }} />
            {s.label}
            {byStatus[s.key] != null && (
              <strong style={{ color: 'var(--text)', marginLeft: 2 }}>{byStatus[s.key]}</strong>
            )}
          </span>
        ))}
      </div>
    </>
  )

  return (
    <ChartCard title="Findings by Status" description="Distribution across all statuses" footer={footer}>
      {chartData.length === 0 ? (
        <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          No findings yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              outerRadius={88}
              dataKey="value"
              nameKey="name"
              stroke="0"
            >
              {chartData.map((entry) => (
                <Cell key={entry.name} fill={entry.fill} />
              ))}
            </Pie>
            <RTooltip
              cursor={false}
              formatter={(v: number, name: string) => [`${v}`, name]}
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: '0.75rem' }}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  )
}

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low', 'info']
const STATUS_OPTIONS = ['open', 'resolved', 'false_positive', 'accepted_risk']

function statusPillClass(status: string): string {
  const map: Record<string, string> = {
    open: 'status-pill open',
    resolved: 'status-pill resolved',
    false_positive: 'status-pill false-positive',
    accepted_risk: 'status-pill accepted-risk',
  }
  return map[status] ?? 'status-pill'
}

export default function Findings() {
  const [severity, setSeverity] = useState('')
  const [status, setStatus] = useState('')
  const [platform, setPlatform] = useState('')
  const [connectorId, setConnectorId] = useState('')
  const [search, setSearch] = useState('')
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null)

  const { data: connectors } = useConnectors()

  const { data, isLoading, isError, refetch } = useFindings({
    severity: severity || undefined,
    status: status || undefined,
    platform: platform || undefined,
    connector_id: connectorId || undefined,
    limit: 200,
  })

  const findings = useMemo(() => {
    if (!data) return []
    if (!search.trim()) return data
    const q = search.toLowerCase()
    return data.filter(
      (f) =>
        f.resource_identifier.toLowerCase().includes(q) ||
        (f.rule_name ?? '').toLowerCase().includes(q) ||
        f.rule_id.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q),
    )
  }, [data, search])

  const hasFilters = severity || status || platform || connectorId || search

  function clearFilters() {
    setSeverity('')
    setStatus('')
    setPlatform('')
    setConnectorId('')
    setSearch('')
  }

  const uniquePlatforms = useMemo(() => {
    const ps = new Set(data?.map((f) => f.platform) ?? [])
    return Array.from(ps).sort((a, b) => a.localeCompare(b))
  }, [data])

  return (
    <div>
      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14, marginBottom: 14 }}>
        <SeverityDonut />
        <StatusDonut />
      </div>

      {/* Filter bar */}
      <div className="filter-bar">
        {/* Search */}
        <div style={{ position: 'relative', flex: 1, minWidth: 180, maxWidth: 280 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input
            type="text"
            className="input"
            style={{ paddingLeft: 30, paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem' }}
            placeholder="Search findings…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Severity */}
        <div style={{ position: 'relative' }}>
          <select
            className="select"
            style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', paddingRight: 28, minWidth: 130 }}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="">All severities</option>
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
          <Filter size={11} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
        </div>

        {/* Status */}
        <div style={{ position: 'relative' }}>
          <select
            className="select"
            style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', paddingRight: 28, minWidth: 130 }}
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{statusLabel(s)}</option>
            ))}
          </select>
          <Filter size={11} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
        </div>

        {/* Platform */}
        {uniquePlatforms.length > 0 && (
          <div style={{ position: 'relative' }}>
            <select
              className="select"
              style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', paddingRight: 28, minWidth: 130 }}
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
            >
              <option value="">All platforms</option>
              {uniquePlatforms.map((p) => (
                <option key={p} value={p}>{platformLabel(p)}</option>
              ))}
            </select>
            <Filter size={11} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          </div>
        )}

        {/* Connector */}
        {connectors && connectors.length > 0 && (
          <div style={{ position: 'relative' }}>
            <select
              className="select"
              style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', paddingRight: 28, minWidth: 150 }}
              value={connectorId}
              onChange={(e) => setConnectorId(e.target.value)}
            >
              <option value="">All connectors</option>
              {connectors.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name}</option>
              ))}
            </select>
            <Filter size={11} style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          </div>
        )}

        {hasFilters && (
          <button onClick={clearFilters} className="btn-ghost" style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem' }}>
            <X size={13} />
            Clear
          </button>
        )}

        <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {isLoading ? '…' : `${findings.length} findings`}
        </span>
      </div>

      {/* Error */}
      {isError && (
        <div style={{
          borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12,
          background: 'color-mix(in oklch, var(--sev-critical) 10%, transparent)',
          border: '1px solid color-mix(in oklch, var(--sev-critical) 25%, transparent)',
          marginBottom: 14,
        }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', flex: 1 }}>Failed to load findings.</p>
          <button onClick={() => refetch()} style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
            Retry
          </button>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="findings-table">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="finding-row" style={{ cursor: 'default' }}>
              <div className="skeleton" style={{ height: 20, borderRadius: 6 }} />
              <div className="skeleton" style={{ height: 14 }} />
              <div className="skeleton" style={{ height: 14, width: 80 }} />
              <div className="skeleton" style={{ height: 20, borderRadius: 20, width: 70 }} />
              <div className="skeleton" style={{ height: 14, width: 60 }} />
              <div />
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {!isLoading && !isError && (
        findings.length === 0 ? (
          <div className="empty-state">
            <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
              No findings match your filters
            </p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              {hasFilters ? (
                <button onClick={clearFilters} style={{ color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                  Clear filters to see all findings
                </button>
              ) : 'Run a scan to detect findings'}
            </p>
          </div>
        ) : (
          <div className="findings-table">
            {/* Table head */}
            <div className="table-head finding-row-head" style={{ display: 'grid' }}>
              <span>Severity</span>
              <span>Rule / Resource</span>
              <span>Platform</span>
              <span>Status</span>
              <span>Last seen</span>
              <span />
            </div>

            {findings.map((f) => (
              <button
                key={f.id}
                onClick={() => setSelectedFinding(f)}
                className="finding-row"
                style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none' }}
              >
                <SeverityBadge severity={f.severity} />
                <div style={{ minWidth: 0 }}>
                  <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.rule_name ?? f.rule_id}
                  </p>
                  <p style={{ fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 2 }}>
                    {f.resource_identifier}
                  </p>
                </div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{platformLabel(f.platform)}</span>
                <span className={statusPillClass(f.status)}>{statusLabel(f.status)}</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                  {formatRelative(f.last_detected)}
                </span>
                <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
              </button>
            ))}
          </div>
        )
      )}

      <FindingDrawer finding={selectedFinding} onClose={() => setSelectedFinding(null)} />
    </div>
  )
}
