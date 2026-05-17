import { useState } from 'react'
import { ShieldCheck, Download, RefreshCw, Loader, CheckCircle2, XCircle, HelpCircle } from 'lucide-react'
import {
  useComplianceReport,
  useComplianceScores,
  useGenerateReport,
  type ComplianceStandard,
  type PlatformScore,
} from '../api/compliance'
import { ScoreGauge } from '../components/compliance/ScoreGauge'
import { TrendChart } from '../components/compliance/TrendChart'
import { formatRelative } from '../lib/utils'

const PLATFORMS = ['github', 'entra', 'jira', 'slack']
const PDF_BASE = '/api/v1'

// ── Helpers ────────────────────────────────────────────────────────────────────

function Stat({ icon, value, label }: Readonly<{ icon: React.ReactNode; value: number; label: string }>) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      {icon}
      <span style={{ fontSize: '0.75rem', color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
        <strong>{value}</strong> <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      </span>
    </div>
  )
}

// ── Framework card with download button ───────────────────────────────────────

function FrameworkCard({ standard, platform }: Readonly<{ standard: ComplianceStandard; platform: string }>) {
  const generate = useGenerateReport()

  function handleDownload() {
    generate.mutate(
      { platform, framework: standard.id, with_ai_narrative: true },
      {
        onSuccess: (data) => {
          const link = document.createElement('a')
          link.href = `${PDF_BASE}/compliance/reports/${data.id}/pdf`
          link.download = `compliance_${platform}_${standard.id}_${data.id}.pdf`
          document.body.appendChild(link)
          link.click()
          document.body.removeChild(link)
        },
      },
    )
  }

  return (
    <div className="card" style={{ padding: '20px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <ScoreGauge score={standard.score} size={72} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>
            {standard.name}
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 8 }}>
            {standard.description}
          </p>
          {standard.total_controls > 0 ? (
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <Stat icon={<CheckCircle2 size={12} style={{ color: 'var(--ok)' }} />} value={standard.passing_controls} label="passing" />
              <Stat icon={<XCircle size={12} style={{ color: 'var(--sev-critical)' }} />} value={standard.failing_controls} label="failing" />
              {standard.not_applicable_controls > 0 && (
                <Stat icon={<HelpCircle size={12} style={{ color: 'var(--text-muted)' }} />} value={standard.not_applicable_controls} label="N/A" />
              )}
            </div>
          ) : (
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>No rules mapped</p>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid var(--border)', paddingTop: 12 }}>
        <button
          onClick={handleDownload}
          disabled={generate.isPending}
          className="btn-primary btn-sm"
        >
          {generate.isPending
            ? <><Loader size={12} className="animate-spin" /> Generating…</>
            : <><Download size={12} /> Download Report</>}
        </button>
      </div>

      {generate.isError && (
        <p style={{ fontSize: '0.6875rem', color: 'var(--sev-critical)', marginTop: -6 }}>
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
  const color = score >= 75 ? 'var(--ok)' : score >= 50 ? 'var(--sev-medium)' : 'var(--sev-critical)'

  return (
    <div style={{
      display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center',
      padding: '16px 20px', background: 'var(--surface)',
      border: '1px solid var(--border)', borderRadius: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <ScoreGauge score={score} size={64} />
        <div>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Overall Compliance</p>
          <p style={{ fontSize: '1.375rem', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
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
        ].map(({ label, value, color: c }) => (
          <div key={label}>
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginBottom: 2 }}>{label}</p>
            <p style={{ fontSize: '1.125rem', fontWeight: 700, color: c, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Per-platform score card ────────────────────────────────────────────────────

function PlatformScoreCard({ score }: Readonly<{ score: PlatformScore }>) {
  const color = score.score >= 75 ? 'var(--ok)' : score.score >= 50 ? 'var(--sev-medium)' : 'var(--sev-critical)'
  return (
    <div style={{
      padding: '12px 16px', borderRadius: 10, background: 'var(--surface-2)',
      border: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <span style={{ fontSize: '1.125rem', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', minWidth: 52 }}>
        {score.score}%
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text)' }}>{score.framework}</p>
        <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
          {score.platform} · {score.passed_rules}/{score.total_rules} rules
        </p>
      </div>
    </div>
  )
}

function SectionLabel({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <p style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
      {children}
    </p>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Compliance() {
  const [platform, setPlatform] = useState('github')
  const { data, isLoading, error, refetch } = useComplianceReport()
  const { data: scores } = useComplianceScores()

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Compliance</h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>
            Control coverage across CIS, SOC 2, ISO 27001, and NIST CSF
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Report platform:</span>
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            style={{
              padding: '5px 10px', borderRadius: 8, border: '1px solid var(--border)',
              background: 'var(--surface)', color: 'var(--text)', fontSize: '0.8125rem',
            }}
          >
            {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {isLoading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="skeleton" style={{ height: 90, borderRadius: 12 }} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
            {[1, 2, 3, 4].map((i) => <div key={i} className="skeleton" style={{ height: 170, borderRadius: 12 }} />)}
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          <OverallStrip score={data.overall_score} standards={data.standards} />

          {/* Framework cards */}
          <div>
            <SectionLabel>Frameworks</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
              {data.standards.map((std) => (
                <FrameworkCard key={std.id} standard={std} platform={platform} />
              ))}
            </div>
          </div>

          {/* Per-platform breakdown */}
          {scores && scores.length > 0 && (
            <div>
              <SectionLabel>Per-Platform Breakdown</SectionLabel>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
                {scores.map((s) => (
                  <PlatformScoreCard key={`${s.platform}-${s.framework}`} score={s} />
                ))}
              </div>
            </div>
          )}

          {data.last_updated && (
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textAlign: 'right', marginTop: -16 }}>
              Updated {formatRelative(data.last_updated)}
            </p>
          )}

          {/* Trends chart */}
          <div>
            <SectionLabel>Compliance Trends</SectionLabel>
            <TrendChart />
          </div>
        </div>
      )}
    </div>
  )
}
