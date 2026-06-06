import { Link } from 'react-router-dom'
import { ShieldCheck, AlertTriangle, Plug, ArrowRight, Users, ShieldAlert } from 'lucide-react'
import {
  RadialBarChart, RadialBar, PolarRadiusAxis, Label,
  AreaChart, Area, XAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import type { ScanRun, IdentityPlatform } from '../api/types'
import { useFindingSummary, useFindingsByCategory } from '../api/findings'
import { useConnectors } from '../api/connectors'
import { useScanRuns } from '../api/rules'
import { useIdentityPlatforms, useCrossPlatformUsers } from '../api/identities'
import { usePostureScore, usePrioritizedActions } from '../api/activityLogs'
import SeverityBadge from '../components/findings/SeverityBadge'
import PlatformLogo from '../components/shared/PlatformLogo'
import { formatNumber, formatRelative, calcPostureScore, platformLabel } from '../lib/utils'

// ── Posture radial chart — subtle ring, no sparkline ───────────────────────
interface PostureLabelProps { viewBox?: { cx?: number; cy?: number }; score: number; color: string }
function PostureScoreLabel({ viewBox, score, color }: Readonly<PostureLabelProps>) {
  if (!viewBox) return null
  const cx = viewBox.cx ?? 0
  const cy = viewBox.cy ?? 0
  return (
    <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle">
      <tspan x={cx} y={cy} style={{ fill: color, fontSize: 28, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{score}</tspan>
      <tspan x={cx} y={cy + 20} style={{ fill: 'var(--text-muted)', fontSize: 11 }}>/ 100</tspan>
    </text>
  )
}

function PostureRadial({ score, color }: Readonly<{ score: number; color: string }>) {
  const data = [{ value: score }]
  return (
    <RadialBarChart width={148} height={148} data={data}
      startAngle={90} endAngle={90 - (score / 100) * 360}
      innerRadius={50} outerRadius={68} style={{ margin: 'auto' }}
    >
      <RadialBar dataKey="value" cornerRadius={6} fill={color}
        background={{ fill: 'color-mix(in oklch, var(--border) 80%, transparent)' }} />
      <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
        <Label content={<PostureScoreLabel score={score} color={color} />} />
      </PolarRadiusAxis>
    </RadialBarChart>
  )
}

// ── Active connectors stacked half-circle ───────────────────────────────────
interface ConnLabelProps { viewBox?: { cx?: number; cy?: number }; active: number; total: number; allOk: boolean }
function ConnectorsLabel({ viewBox, active, total, allOk }: Readonly<ConnLabelProps>) {
  if (!viewBox) return null
  const cx = viewBox.cx ?? 100
  const cy = viewBox.cy ?? 104
  const fill = allOk ? 'var(--ok)' : 'var(--accent)'
  return (
    <text x={cx} textAnchor="middle">
      <tspan x={cx} y={cy - 8} style={{ fill, fontSize: 26, fontWeight: 700 }}>{active}</tspan>
      <tspan x={cx} y={cy + 12} style={{ fill: 'var(--text-muted)', fontSize: 11 }}>of {total}</tspan>
    </text>
  )
}

function ConnectorsRadial({ active, total }: Readonly<{ active: number; total: number }>) {
  const inactive = Math.max(0, total - active)
  const data = [{ active, inactive }]
  const allOk = total > 0 && active === total
  return (
    <RadialBarChart width={200} height={124} cx={100} cy={104} data={data}
      startAngle={180} endAngle={0} innerRadius={60} outerRadius={86} style={{ margin: 'auto' }}
    >
      <RadialBar dataKey="inactive" stackId="a" cornerRadius={4} fill="color-mix(in oklch, var(--border) 120%, transparent)" />
      <RadialBar dataKey="active" stackId="a" cornerRadius={4} fill={allOk ? 'var(--ok)' : 'var(--accent)'} />
      <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
        <Label content={<ConnectorsLabel active={active} total={total} allOk={allOk} />} />
      </PolarRadiusAxis>
    </RadialBarChart>
  )
}

// ── Findings trend (findings_count per completed scan run) ──────────────────
function FindingsTrendChart({ scanRuns }: Readonly<{ scanRuns: ScanRun[] }>) {
  const data = [...scanRuns]
    .filter((r) => r.completed_at)
    .sort((a, b) => new Date(a.completed_at ?? '').getTime() - new Date(b.completed_at ?? '').getTime())
    .slice(-20)
    .map((r) => ({
      label: formatRelative(r.completed_at),
      findings: r.findings_count ?? 0,
    }))

  if (data.length === 0) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120 }}>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>No scan data yet</p>
    </div>
  )

  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={data} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
        <defs>
          <linearGradient id="findingsGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.25} />
            <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
        <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
          tickMargin={6} interval="preserveStartEnd" />
        <Tooltip
          cursor={{ stroke: 'var(--border)', strokeWidth: 1 }}
          contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: 'var(--text-muted)', marginBottom: 4 }}
          itemStyle={{ color: 'var(--accent)' }}
          formatter={(v: number) => [v, 'Open findings']}
        />
        <Area type="linear" dataKey="findings" stroke="var(--accent)" strokeWidth={2}
          fill="url(#findingsGrad)" dot={{ r: 3, fill: 'var(--accent)', strokeWidth: 0 }}
          activeDot={{ r: 4, fill: 'var(--accent)' }} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Stacked severity bar ────────────────────────────────────────────────────
interface SevCounts { critical: number; high: number; medium: number; low: number }

function SeverityBar({ critical, high, medium, low }: Readonly<SevCounts>) {
  const total = critical + high + medium + low || 1
  const segs = [
    { value: critical, color: 'var(--sev-critical)', label: 'Critical' },
    { value: high,     color: 'var(--sev-high)',     label: 'High' },
    { value: medium,   color: 'var(--sev-medium)',   label: 'Medium' },
    { value: low,      color: 'var(--sev-low)',      label: 'Low' },
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', background: 'var(--surface-2)' }}>
        {segs.map((s) =>
          s.value > 0 ? (
            <div key={s.label} style={{ width: `${(s.value / total) * 100}%`, background: s.color, transition: 'width 0.5s' }} />
          ) : null
        )}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px' }}>
        {segs.map((s) => (
          <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, flexShrink: 0 }} />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {s.label} <strong style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{s.value}</strong>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Connected Platforms card (replaces Identities KPI + Connector Coverage) ───
function ConnectedPlatformRow({ p }: Readonly<{ p: IdentityPlatform }>) {
  const { data: posture } = usePostureScore(p.platform)
  const alerts = posture?.total_open_findings ?? 0
  return (
    <Link
      to={`/identities/${p.platform}`}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '8px 10px', borderRadius: 8, textDecoration: 'none',
        transition: 'background 0.12s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-hover)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <PlatformLogo platform={p.platform} size={28} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {p.connector_name || platformLabel(p.platform)}
        </p>
        <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 1 }}>
          {platformLabel(p.platform)}
        </p>
      </div>
      {alerts > 0 ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0, padding: '3px 8px', borderRadius: 20, background: 'color-mix(in oklch, var(--sev-medium) 10%, transparent)' }}>
          <AlertTriangle size={11} style={{ color: 'var(--sev-medium)' }} />
          <span style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--sev-medium)', fontVariantNumeric: 'tabular-nums' }}>{alerts}</span>
        </div>
      ) : (
        <span className="status-dot ok" />
      )}
    </Link>
  )
}

function ConnectedPlatformsCard() {
  const { data: platforms, isLoading } = useIdentityPlatforms()
  let body: React.ReactNode
  if (isLoading) {
    body = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 36, borderRadius: 8 }} />)}
      </div>
    )
  } else if (!platforms || platforms.length === 0) {
    body = (
      <div style={{ textAlign: 'center', padding: '16px 0' }}>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>No platforms synced yet.</p>
        <Link to="/connectors" style={{ fontSize: '0.75rem', color: 'var(--accent)', marginTop: 6, display: 'inline-block' }}>Add a connector →</Link>
      </div>
    )
  } else {
    body = (
      <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {platforms.map((p) => (
          <li key={p.connector_id}><ConnectedPlatformRow p={p} /></li>
        ))}
      </ul>
    )
  }
  return (
    <div className="card" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>Connected Platforms</h2>
        <Link to="/identities" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--text-muted)', textDecoration: 'none' }}>
          Identities <ArrowRight size={12} />
        </Link>
      </div>
      {body}
    </div>
  )
}

// ── Findings by category donut chart ───────────────────────────────────────
const CATEGORY_COLORS: Record<string, string> = {
  'Identity / Authentication': '#6366f1',
  'Data Exposure':             '#ef4444',
  'Third-Party':               '#f59e0b',
  'Shadow IT':                 '#8b5cf6',
  'Others':                    '#94a3b8',
}

function FindingsByCategoryChart() {
  const { data, isLoading } = useFindingsByCategory()

  if (isLoading) {
    return (
      <div className="kpi-card" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="skeleton" style={{ width: 100, height: 100, borderRadius: '50%' }} />
      </div>
    )
  }

  const entries = Object.entries(data ?? {}).filter(([, v]) => v > 0)
  const total = entries.reduce((s, [, v]) => s + v, 0)

  if (total === 0) {
    return (
      <div className="kpi-card" style={{ alignItems: 'center', justifyContent: 'center', gap: 6 }}>
        <div className="kpi-top" style={{ width: '100%' }}>
          <span className="kpi-label">Finding Types</span>
        </div>
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', textAlign: 'center' }}>No open findings</p>
      </div>
    )
  }

  const pieData = entries.map(([name, value]) => ({ name, value }))

  return (
    <div className="kpi-card" style={{ gap: 4 }}>
      <div className="kpi-top" style={{ width: '100%' }}>
        <span className="kpi-label">Finding Types</span>
      </div>
      {/* Donut — no Legend inside so the circle stays centered */}
      <ResponsiveContainer width="100%" height={110}>
        <PieChart>
          <Pie
            data={pieData}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={30}
            outerRadius={50}
            paddingAngle={2}
            strokeWidth={0}
          >
            {pieData.map((entry) => (
              <Cell key={entry.name} fill={CATEGORY_COLORS[entry.name] ?? '#94a3b8'} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number, name: string) => [value, name]}
            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 11 }}
          />
        </PieChart>
      </ResponsiveContainer>
      {/* External compact legend */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 2 }}>
        {pieData.map((entry) => (
          <div key={entry.name} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: CATEGORY_COLORS[entry.name] ?? '#94a3b8', flexShrink: 0 }} />
            <span style={{ fontSize: '0.5625rem', color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {entry.name}
            </span>
            <span style={{ fontSize: '0.5625rem', fontWeight: 700, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
              {entry.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── KPI card ────────────────────────────────────────────────────────────────
function KpiCard({ icon, label, value, sub, children, color }: Readonly<{
  icon: React.ReactNode; label: string; value: React.ReactNode
  sub?: string; children?: React.ReactNode; color?: string
}>) {
  return (
    <div className="kpi-card">
      <div className="kpi-top">
        <span className="kpi-label">{label}</span>
        <span className="kpi-icon">{icon}</span>
      </div>
      <div className="kpi-value" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
      {children}
    </div>
  )
}


// ── KPI strip sub-components ────────────────────────────────────────────────

type SummaryQ   = ReturnType<typeof useFindingSummary>
type PostureQ   = ReturnType<typeof usePostureScore>
type ScanRunsQ  = ReturnType<typeof useScanRuns>

function postureColor(score: number | null): string {
  if (score === null) return 'var(--text-muted)'
  if (score >= 80) return 'var(--ok)'
  if (score >= 60) return 'var(--sev-medium)'
  if (score >= 40) return 'var(--sev-high)'
  return 'var(--sev-critical)'
}

function connectorHealthLabel(total: number, active: number): string {
  if (total === 0) return 'No connectors yet'
  if (total - active > 0) return `${total - active} need attention`
  return 'All connectors healthy'
}

function PostureScoreKpi({ summaryQ, postureQ }: Readonly<{ summaryQ: SummaryQ; postureQ: PostureQ }>) {
  const clientScore = summaryQ.data ? calcPostureScore(summaryQ.data) : null
  const score = postureQ.data?.score ?? clientScore
  const color = postureColor(score)
  if (summaryQ.isLoading) return <div className="kpi-card"><div className="skeleton" style={{ height: 148, borderRadius: 8 }} /></div>
  return (
    <div className="kpi-card" style={{ alignItems: 'center', gap: 4 }}>
      <div className="kpi-top" style={{ width: '100%' }}>
        <span className="kpi-label">Posture Score</span>
        <span className="kpi-icon"><ShieldCheck size={16} /></span>
      </div>
      <PostureRadial score={score ?? 0} color={color} />
      <div className="kpi-sub" style={{ textAlign: 'center', marginTop: 2 }}>
        {postureQ.data ? 'Impact-weighted score' : 'Lower open findings = higher score'}
      </div>
    </div>
  )
}

function OpenFindingsKpi({ summaryQ }: Readonly<{ summaryQ: SummaryQ }>) {
  if (summaryQ.isLoading) return <div className="kpi-card"><div className="skeleton" style={{ height: 140, borderRadius: 8 }} /></div>
  if (!summaryQ.data) return null
  const sev = summaryQ.data.open_by_severity ?? { critical: 0, high: 0, medium: 0, low: 0 }
  return (
    <KpiCard icon={<AlertTriangle size={16} />} label="Open Findings" value={formatNumber(summaryQ.data.total)} sub="Across all connected platforms">
      <SeverityBar {...sev} />
    </KpiCard>
  )
}

function ActiveConnectorsKpi({ connectorsQ }: Readonly<{ connectorsQ: ConnectorsQ }>) {
  const connectors = connectorsQ.data ?? []
  const active = connectors.filter((c) => c.connection_ok === true).length
  if (connectorsQ.isLoading) return <div className="kpi-card"><div className="skeleton" style={{ height: 148, borderRadius: 8 }} /></div>
  return (
    <div className="kpi-card" style={{ alignItems: 'center', gap: 4 }}>
      <div className="kpi-top" style={{ width: '100%' }}>
        <span className="kpi-label">Active Connectors</span>
        <span className="kpi-icon"><Plug size={16} /></span>
      </div>
      <ConnectorsRadial active={active} total={connectors.length} />
      <div className="kpi-sub" style={{ textAlign: 'center', marginTop: 2 }}>
        {connectorHealthLabel(connectors.length, active)}
      </div>
    </div>
  )
}

function FindingsTrendCard({ scanRunsQ }: Readonly<{ scanRunsQ: ScanRunsQ }>) {
  return (
    <div className="card" style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>Open Findings Trend</h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
            Total open findings per connector after each completed scan
          </p>
        </div>
        <Link to="/scan-runs" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--text-muted)', textDecoration: 'none' }}>
          All scans <ArrowRight size={12} />
        </Link>
      </div>
      <FindingsTrendChart scanRuns={scanRunsQ.data ?? []} />
    </div>
  )
}

// ── Extracted card components to keep Dashboard cognitive complexity ≤ 15 ────

type PrioritizedQ = ReturnType<typeof usePrioritizedActions>
type ConnectorsQ  = ReturnType<typeof useConnectors>

function PrioritizedActionsCard({ q }: Readonly<{ q: PrioritizedQ }>) {
  const actions = q.data?.actions ?? []
  let body: React.ReactNode
  if (q.isLoading) {
    body = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[1, 2, 3].map((i) => (
          <div key={i} style={{ display: 'flex', gap: 10 }}>
            <div className="skeleton" style={{ width: 60, height: 20 }} />
            <div className="skeleton" style={{ flex: 1, height: 20 }} />
          </div>
        ))}
      </div>
    )
  } else if (actions.length) {
    body = (
      <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
        {actions.map((a, i) => {
          // posture_gain comes from the API — computed live from open findings
          // every call, so it stays accurate after every sync. Never hardcoded.
          const gain = a.posture_gain ?? 0
          return (
            <li key={a.finding_id} style={{
              display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 0',
              borderBottom: i < actions.length - 1 ? '1px solid var(--border)' : 'none',
            }}>
              <SeverityBadge severity={a.severity} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {a.title}
                </p>
                {a.impact_summary && (
                  <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 2 }}>
                    {a.impact_summary}
                  </p>
                )}
                <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1 }}>
                  {a.resource_identifier}
                </p>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{platformLabel(a.platform)}</span>
                {gain > 0 && (
                  <span
                    title="Estimated posture-score improvement if this finding is resolved"
                    style={{
                      fontSize: '0.625rem', fontWeight: 700, padding: '2px 6px', borderRadius: 10,
                      background: 'color-mix(in oklch, var(--ok) 12%, transparent)',
                      color: 'var(--ok)',
                    }}
                  >
                    +{gain.toFixed(1)}% posture
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    )
  } else {
    body = (
      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', padding: '16px 0', textAlign: 'center' }}>
        No open findings — great posture!
      </p>
    )
  }
  return (
    <div className="card" style={{ padding: '20px 24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>Prioritized Actions</h2>
          {q.data && (
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2 }}>
              {q.data.source === 'ollama' ? 'AI-ranked' : 'Ranked by severity & impact'} · {q.data.total_open_findings} open findings
            </p>
          )}
        </div>
        <Link to="/findings" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--text-muted)', textDecoration: 'none' }}>
          View all <ArrowRight size={12} />
        </Link>
      </div>
      {body}
    </div>
  )
}

type CrossUsersQ = ReturnType<typeof useCrossPlatformUsers>

function TopRiskyUsersCard({ q }: Readonly<{ q: CrossUsersQ }>) {
  const users = (q.data ?? []).slice(0, 3)
  let body: React.ReactNode

  if (q.isLoading) {
    body = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 56, borderRadius: 8 }} />)}
      </div>
    )
  } else if (users.length === 0) {
    body = (
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', padding: '12px 0', textAlign: 'center' }}>
        No users found on multiple platforms yet.
      </p>
    )
  } else {
    body = (
      <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {users.map((u, idx) => (
          <li key={u.email} style={{
            padding: '10px 12px', borderRadius: 10,
            background: 'var(--surface-2)',
            border: '1px solid var(--border)',
            display: 'flex', flexDirection: 'column', gap: 6,
          }}>
            {/* Top row: rank + name + admin */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                flexShrink: 0,
                width: 20, height: 20, borderRadius: '50%',
                background: 'color-mix(in oklch, var(--sev-critical) 15%, transparent)',
                color: 'var(--sev-critical)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.6875rem', fontWeight: 700,
              }}>{idx + 1}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{
                  fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {u.display_name}
                </p>
                <p style={{
                  fontSize: '0.625rem', color: 'var(--text-muted)',
                  fontFamily: 'monospace',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {u.email}
                </p>
              </div>
              {u.is_admin && (
                <span style={{
                  fontSize: '0.5625rem', fontWeight: 700,
                  padding: '2px 6px', borderRadius: 4,
                  background: 'color-mix(in oklch, var(--sev-critical) 15%, transparent)',
                  color: 'var(--sev-critical)',
                  textTransform: 'uppercase', letterSpacing: '0.04em',
                  flexShrink: 0,
                }}>Admin</span>
              )}
            </div>

            {/* Platforms + risk score */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {u.platforms.map((p) => (
                <span key={p} style={{
                  fontSize: '0.5625rem', fontWeight: 600,
                  padding: '2px 6px', borderRadius: 4,
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  color: 'var(--text-muted)',
                  textTransform: 'capitalize',
                }}>{p}</span>
              ))}
              <span style={{ flex: 1 }} />
              {u.open_findings > 0 && (
                <span style={{
                  fontSize: '0.625rem', color: 'var(--text-muted)',
                  fontVariantNumeric: 'tabular-nums',
                }}>
                  <strong style={{ color: 'var(--sev-critical)' }}>{u.open_findings}</strong> finding{u.open_findings !== 1 ? 's' : ''}
                </span>
              )}
              <span style={{
                fontSize: '0.625rem', fontWeight: 700,
                padding: '2px 6px', borderRadius: 4,
                background: 'color-mix(in oklch, var(--sev-critical) 12%, transparent)',
                color: 'var(--sev-critical)',
                fontVariantNumeric: 'tabular-nums',
              }}>
                risk {u.risk_score}
              </span>
            </div>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="card" style={{ padding: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <ShieldAlert size={14} style={{ color: 'var(--sev-critical)' }} />
          <h2 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>Top Risky Identities</h2>
        </div>
        <Link to="/identities" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.6875rem', color: 'var(--text-muted)', textDecoration: 'none' }}>
          <Users size={11} /> All <ArrowRight size={11} />
        </Link>
      </div>
      <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: -10, marginBottom: 10 }}>
        Users present on 2+ platforms, ranked by risk
      </p>
      {body}
    </div>
  )
}

export default function Dashboard() {
  const summaryQ = useFindingSummary()
  const connectorsQ = useConnectors()
  const prioritizedQ = usePrioritizedActions(undefined, 5)
  const crossUsersQ = useCrossPlatformUsers(50)
  const scanRunsQ = useScanRuns()
  const postureQ = usePostureScore()

  return (
    <div>
      {/* KPI strip */}
      <div className="kpi-strip">
        <PostureScoreKpi summaryQ={summaryQ} postureQ={postureQ} />
        <OpenFindingsKpi summaryQ={summaryQ} />
        <ActiveConnectorsKpi connectorsQ={connectorsQ} />
        <FindingsByCategoryChart />
      </div>

      {/* Trend + Connected Platforms side by side */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 260px)', gap: 20, marginBottom: 20, alignItems: 'start' }}>
        <FindingsTrendCard scanRunsQ={scanRunsQ} />
        <ConnectedPlatformsCard />
      </div>

      {/* Main 2-col grid: actions | top risky identities */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 320px)', gap: 20, alignItems: 'start' }}>
        <PrioritizedActionsCard q={prioritizedQ} />
        <TopRiskyUsersCard q={crossUsersQ} />
      </div>
    </div>
  )
}
