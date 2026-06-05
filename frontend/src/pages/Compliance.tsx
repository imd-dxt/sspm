import type { ReactNode } from 'react'
import { RadialBarChart, RadialBar, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { ShieldCheck, Download, RefreshCw, Loader, CheckCircle2, XCircle, HelpCircle, FileDown } from 'lucide-react'
import {
  useComplianceReport,
  useComplianceScores,
  useComplianceReports,
  useGenerateReport,
  downloadFullPostureReport,
  downloadReportById,
  type ComplianceStandard,
  type PlatformScore,
  type StoredReport,
} from '../api/compliance'
import { useConnectors } from '../api/connectors'
import { ScoreGauge } from '../components/compliance/ScoreGauge'
import { TrendChart } from '../components/compliance/TrendChart'
import { formatRelative } from '../lib/utils'

const RADIAL_PALETTE = [
  '#6366f1', '#22c55e', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16',
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function Stat({ icon, value, label }: Readonly<{ icon: ReactNode; value: number; label: string }>) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      {icon}
      <span style={{ fontSize: '0.75rem', color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
        <strong>{value}</strong> <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      </span>
    </div>
  )
}

function SectionLabel({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <p style={{
      fontSize: '0.6875rem', fontWeight: 700, color: 'var(--text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12,
    }}>
      {children}
    </p>
  )
}

// ── Framework card ─────────────────────────────────────────────────────────────
// The download uses the first available platform. No per-card selector — the
// Platform Breakdown section already gives per-platform visibility.

function FrameworkCard({ standard, latestReport }: Readonly<{ standard: ComplianceStandard; latestReport?: StoredReport | null }>) {
  const generate = useGenerateReport()

  function handleDownload() {
    // If a pre-generated report exists, download it via authenticated fetch
    if (latestReport) {
      void downloadReportById(
        latestReport.id,
        `compliance_all_${standard.id}_${latestReport.id}.pdf`,
      )
      return
    }
    // Otherwise generate it, then download the new file
    generate.mutate(
      { platform: 'all', framework: standard.id, with_ai_narrative: true },
      {
        onSuccess: (report) => {
          void downloadReportById(
            report.id,
            `compliance_all_${standard.id}_${report.id}.pdf`,
          )
        },
      },
    )
  }

  const hasControls = standard.total_controls > 0

  return (
    <div className="card" style={{
      padding: '18px 20px', display: 'flex', flexDirection: 'column',
      gap: 0, minHeight: 160,
    }}>
      {/* Top: gauge + info */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flex: 1 }}>
        <ScoreGauge score={standard.score} size={62} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)', marginBottom: 2, lineHeight: 1.2 }}>
            {standard.name}
          </h3>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginBottom: 10, lineHeight: 1.4 }}>
            {standard.description}
          </p>
          {/* Stats row — always shown */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Stat
              icon={<CheckCircle2 size={11} style={{ color: 'var(--ok)' }} />}
              value={standard.passing_controls}
              label="passing"
            />
            <Stat
              icon={<XCircle size={11} style={{ color: 'var(--sev-critical)' }} />}
              value={standard.failing_controls}
              label="failing"
            />
            {hasControls && standard.not_applicable_controls > 0 && (
              <Stat
                icon={<HelpCircle size={11} style={{ color: 'var(--text-muted)' }} />}
                value={standard.not_applicable_controls}
                label="N/A"
              />
            )}
            {!hasControls && (
              <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No rules mapped
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
        borderTop: '1px solid var(--border)', paddingTop: 10, marginTop: 12,
      }}>
        <button onClick={handleDownload} disabled={generate.isPending} className="btn-primary btn-sm">
          {generate.isPending
            ? <><Loader size={12} className="animate-spin" /> Generating…</>
            : latestReport
              ? <><Download size={12} /> Download Report</>
              : <><Download size={12} /> Generate &amp; Download</>}
        </button>
      </div>
      {generate.isError && (
        <p style={{ fontSize: '0.6875rem', color: 'var(--sev-critical)', marginTop: 4 }}>
          {generate.error instanceof Error ? generate.error.message : 'Generation failed'}
        </p>
      )}
    </div>
  )
}

// ── Overall strip ─────────────────────────────────────────────────────────────

function OverallStrip({ score, standards }: Readonly<{ score: number; standards: ComplianceStandard[] }>) {
  const totalPassing = standards.reduce((s, x) => s + x.passing_controls, 0)
  const totalFailing = standards.reduce((s, x) => s + x.failing_controls, 0)
  const totalControls = standards.reduce((s, x) => s + x.total_controls, 0)
  const scoreColor = score >= 75 ? 'var(--ok)' : score >= 50 ? 'var(--sev-medium)' : 'var(--sev-critical)'

  return (
    <div style={{
      display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center',
      padding: '14px 20px', background: 'var(--surface)',
      border: '1px solid var(--border)', borderRadius: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <ScoreGauge score={score} size={60} />
        <div>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Overall Compliance</p>
          <p style={{ fontSize: '1.375rem', fontWeight: 700, color: scoreColor, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
            {score}%
          </p>
        </div>
      </div>
      <div style={{ width: 1, background: 'var(--border)', alignSelf: 'stretch', flexShrink: 0 }} />
      <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
        {[
          { label: 'Standards', value: standards.filter((s) => s.total_controls > 0).length, color: 'var(--text)' },
          { label: 'Controls', value: totalControls, color: 'var(--text)' },
          { label: 'Passing', value: totalPassing, color: 'var(--ok)' },
          { label: 'Failing', value: totalFailing, color: 'var(--sev-critical)' },
        ].map(({ label, value, color }) => (
          <div key={label}>
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginBottom: 2 }}>{label}</p>
            <p style={{ fontSize: '1.125rem', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{value}</p>
          </div>
        ))}
      </div>
      <div style={{ marginLeft: 'auto' }}>
        <button
          onClick={() => { void downloadFullPostureReport() }}
          className="btn-primary btn-sm"
          title="Download full GRC posture report (all frameworks × all platforms)"
        >
          <FileDown size={13} /> Full Posture Report
        </button>
      </div>
    </div>
  )
}

// ── Per-platform radial card ──────────────────────────────────────────────────

function PlatformRadialCard({ platform, scores }: Readonly<{ platform: string; scores: PlatformScore[] }>) {
  // Empty state: platform connected but no compliance rules defined yet
  if (scores.length === 0) {
    return (
      <div className="card" style={{
        padding: '18px 20px', flex: '1 1 220px', minWidth: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', gap: 6, minHeight: 140,
      }}>
        <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)', textTransform: 'capitalize' }}>
          {platform}
        </h3>
        <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>No compliance rules</p>
      </div>
    )
  }

  const chartData = scores.map((s, i) => ({
    name: s.framework,
    score: s.score,
    fill: RADIAL_PALETTE[i % RADIAL_PALETTE.length],
  }))
  const avg = Math.round(scores.reduce((sum, s) => sum + s.score, 0) / scores.length)
  const avgColor = avg >= 75 ? 'var(--ok)' : avg >= 50 ? 'var(--sev-medium)' : 'var(--sev-critical)'

  const barSize = 12
  const barGap = 3
  const innerRadius = 18
  const outerRadius = innerRadius + scores.length * (barSize + barGap)

  return (
    <div className="card" style={{ padding: '18px 20px', flex: '1 1 220px', minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
        <div>
          <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)', textTransform: 'capitalize' }}>
            {platform}
          </h3>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>avg across frameworks</p>
        </div>
        <span style={{ fontSize: '1.125rem', fontWeight: 700, color: avgColor, fontVariantNumeric: 'tabular-nums' }}>
          {avg}%
        </span>
      </div>

      <ResponsiveContainer width="100%" height={outerRadius * 2 + 40}>
        <RadialBarChart
          data={chartData}
          startAngle={90}
          endAngle={-270}
          innerRadius={innerRadius}
          outerRadius={outerRadius}
          barSize={barSize}
          barGap={barGap}
          cx="50%"
          cy="50%"
        >
          <RadialBar
            dataKey="score"
            background={{ fill: 'var(--surface-2)' } as Record<string, unknown>}
            cornerRadius={3}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const item = payload[0]
              return (
                <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '6px 10px', fontSize: '0.75rem' }}>
                  <strong style={{ color: 'var(--text)' }}>{(item.payload as { name: string }).name}</strong>
                  <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>{item.value}%</span>
                </div>
              )
            }}
          />
          <Legend
            iconType="circle"
            iconSize={7}
            wrapperStyle={{ fontSize: '0.625rem', paddingTop: 4, lineHeight: '1.7' }}
          />
        </RadialBarChart>
      </ResponsiveContainer>
    </div>
  )
}

function groupByPlatform(scores: PlatformScore[]): Map<string, PlatformScore[]> {
  const map = new Map<string, PlatformScore[]>()
  for (const s of scores) {
    if (!map.has(s.platform)) map.set(s.platform, [])
    map.get(s.platform)!.push(s)
  }
  return map
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Compliance() {
  const { data, isLoading, error, refetch } = useComplianceReport()
  const { data: scores } = useComplianceScores()
  const { data: connectors } = useConnectors()
  const { data: reports } = useComplianceReports()

  // Map framework → most recent "all" platform pre-generated report
  const latestReportByFramework = new Map<string, StoredReport>()
  if (reports) {
    for (const r of reports) {
      if (r.platform === 'all' && !latestReportByFramework.has(r.framework)) {
        latestReportByFramework.set(r.framework, r)
      }
    }
  }

  const platformGroups = scores ? groupByPlatform(scores) : new Map<string, PlatformScore[]>()
  // Only show platforms with a successfully connected connector
  const connectedPlatformNames = [
    ...new Set(connectors?.filter((c) => c.connection_ok === true).map((c) => c.platform_name) ?? []),
  ]
  const allBreakdownPlatforms = [
    ...new Set([...platformGroups.keys(), ...connectedPlatformNames]),
  ]

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Compliance</h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>
            Control coverage across CIS, SOC 2, ISO 27001, and NIST CSF
          </p>
        </div>
      </div>

      {isLoading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="skeleton" style={{ height: 84, borderRadius: 12 }} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
            {[1, 2, 3, 4].map((i) => <div key={i} className="skeleton" style={{ height: 160, borderRadius: 12 }} />)}
          </div>
        </div>
      )}

      {!isLoading && (error || !data) && (
        <div className="card" style={{ padding: 40, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <ShieldCheck size={32} style={{ color: 'var(--text-muted)' }} />
          <p style={{ fontWeight: 600, fontSize: '0.9375rem' }}>Could not load compliance data</p>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', maxWidth: 360 }}>
            {error instanceof Error ? error.message : 'Backend may be starting up.'}
          </p>
          <button onClick={() => refetch()} className="btn-ghost" style={{ marginTop: 4 }}>
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      )}

      {data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <OverallStrip score={data.overall_score} standards={data.standards} />

          {/* Framework cards — unified layout, consistent height via stretch */}
          <div>
            <SectionLabel>Frameworks</SectionLabel>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
              gap: 14,
              alignItems: 'stretch',
            }}>
              {data.standards.map((std) => (
                <FrameworkCard key={std.id} standard={std} latestReport={latestReportByFramework.get(std.id)} />
              ))}
            </div>
          </div>

          {/* Per-platform breakdown — includes all connected platforms */}
          {allBreakdownPlatforms.length > 0 && (
            <div>
              <SectionLabel>Platform Breakdown</SectionLabel>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                {allBreakdownPlatforms.map((plt) => (
                  <PlatformRadialCard
                    key={plt}
                    platform={plt}
                    scores={platformGroups.get(plt) ?? []}
                  />
                ))}
              </div>
            </div>
          )}

          {data.last_updated && (
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textAlign: 'right', marginTop: -12 }}>
              Updated {formatRelative(data.last_updated)}
            </p>
          )}

          {/* Trends */}
          <div>
            <SectionLabel>Compliance Trends</SectionLabel>
            <TrendChart />
          </div>
        </div>
      )}
    </div>
  )
}
