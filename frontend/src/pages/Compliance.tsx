import { useState } from 'react'
import {
  ShieldCheck, LayoutGrid, BookOpen, FileText, Bot, Wrench, TrendingUp,
  CheckCircle2, XCircle, HelpCircle, RefreshCw,
} from 'lucide-react'
import {
  useComplianceReport,
  useComplianceScores,
  type ComplianceStandard,
  type PlatformScore,
} from '../api/compliance'
import { ScoreGauge } from '../components/compliance/ScoreGauge'
import { FrameworkGrid } from '../components/compliance/FrameworkGrid'
import { ReportBuilder } from '../components/compliance/ReportBuilder'
import { AIChatPanel } from '../components/compliance/AIChatPanel'
import { RemediationList } from '../components/compliance/RemediationList'
import { TrendChart } from '../components/compliance/TrendChart'
import { formatRelative } from '../lib/utils'

type Tab = 'overview' | 'frameworks' | 'reports' | 'ai' | 'remediation' | 'trends'

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview',     label: 'Overview',      icon: <LayoutGrid size={14} /> },
  { id: 'frameworks',   label: 'Frameworks',    icon: <BookOpen size={14} /> },
  { id: 'reports',      label: 'Reports',       icon: <FileText size={14} /> },
  { id: 'ai',           label: 'AI Assistant',  icon: <Bot size={14} /> },
  { id: 'remediation',  label: 'Remediation',   icon: <Wrench size={14} /> },
  { id: 'trends',       label: 'Trends',        icon: <TrendingUp size={14} /> },
]

// ── Score card ────────────────────────────────────────────────────────────────

function FrameworkCard({ standard }: Readonly<{ standard: ComplianceStandard }>) {
  return (
    <div className="card" style={{ padding: '20px 22px', display: 'flex', alignItems: 'center', gap: 18 }}>
      <ScoreGauge score={standard.score} size={72} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>
          {standard.name}
        </h3>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 8 }}>
          {standard.description}
        </p>
        {standard.total_controls > 0 && (
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <Stat icon={<CheckCircle2 size={12} style={{ color: 'var(--ok)' }} />} value={standard.passing_controls} label="passing" />
            <Stat icon={<XCircle size={12} style={{ color: 'var(--sev-critical)' }} />} value={standard.failing_controls} label="failing" />
            {standard.unknown_controls > 0 && (
              <Stat icon={<HelpCircle size={12} style={{ color: 'var(--text-muted)' }} />} value={standard.unknown_controls} label="unknown" />
            )}
          </div>
        )}
        {!standard.total_controls && (
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>No rules mapped</p>
        )}
      </div>
    </div>
  )
}

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

// ── Overall strip ─────────────────────────────────────────────────────────────

function OverallStrip({ score, standards }: Readonly<{ score: number; standards: ComplianceStandard[] }>) {
  const totalPassing = standards.reduce((s, x) => s + x.passing_controls, 0)
  const totalFailing = standards.reduce((s, x) => s + x.failing_controls, 0)
  const totalControls = standards.reduce((s, x) => s + x.total_controls, 0)

  return (
    <div style={{
      display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center',
      padding: '16px 20px', background: 'var(--surface)',
      border: '1px solid var(--border)', borderRadius: 12, marginBottom: 24,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <ScoreGauge score={score} size={64} />
        <div>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>Overall Compliance</p>
          <p style={{ fontSize: '1.375rem', fontWeight: 700, color: score >= 75 ? 'var(--ok)' : score >= 50 ? 'var(--sev-medium)' : 'var(--sev-critical)', fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
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
    </div>
  )
}

// ── Platform scores grid (Overview tab) ───────────────────────────────────────

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
        <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>{score.platform} · {score.passed_rules}/{score.total_rules} rules</p>
      </div>
    </div>
  )
}

// ── Tab: Overview ─────────────────────────────────────────────────────────────

function OverviewTab() {
  const { data, isLoading, error, refetch } = useComplianceReport()
  const { data: scores } = useComplianceScores()

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="skeleton" style={{ height: 90, borderRadius: 12 }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
          {[1, 2, 3, 4].map((i) => <div key={i} className="skeleton" style={{ height: 130, borderRadius: 12 }} />)}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
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
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <OverallStrip score={data.overall_score} standards={data.standards} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
        {data.standards.map((std) => <FrameworkCard key={std.id} standard={std} />)}
      </div>
      {scores && scores.length > 0 && (
        <div>
          <p style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
            Per-Platform Breakdown
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
            {scores.map((s) => <PlatformScoreCard key={`${s.platform}-${s.framework}`} score={s} />)}
          </div>
        </div>
      )}
      {data.last_updated && (
        <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textAlign: 'right' }}>
          Updated {formatRelative(data.last_updated)}
        </p>
      )}
    </div>
  )
}

// ── Tab: Frameworks ───────────────────────────────────────────────────────────

function FrameworksTab() {
  const { data, isLoading } = useComplianceReport()
  const [activeStd, setActiveStd] = useState('CIS')

  if (isLoading) return <div className="skeleton" style={{ height: 400, borderRadius: 12 }} />
  if (!data) return null

  const stds = data.standards.filter((s) => s.total_controls > 0)
  if (!stds.length) {
    return <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>No mapped rules found.</p>
  }

  const current = stds.find((s) => s.id === activeStd) ?? stds[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Framework tabs */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {stds.map((s) => (
          <button
            key={s.id}
            onClick={() => setActiveStd(s.id)}
            className={s.id === (current?.id ?? '') ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
          >
            {s.name} · {s.score}%
          </button>
        ))}
      </div>
      {current && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 14 }}>
            <ScoreGauge score={current.score} size={52} />
            <div>
              <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>{current.name}</h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{current.description}</p>
            </div>
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 16 }}>
              {[
                { label: 'Pass', value: current.passing_controls, color: 'var(--ok)' },
                { label: 'Fail', value: current.failing_controls, color: 'var(--sev-critical)' },
                { label: 'Unknown', value: current.unknown_controls, color: 'var(--text-muted)' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ textAlign: 'center' }}>
                  <p style={{ fontSize: '1rem', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums' }}>{value}</p>
                  <p style={{ fontSize: '0.625rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>{label}</p>
                </div>
              ))}
            </div>
          </div>
          <div style={{ padding: 0 }}>
            <FrameworkGrid standard={current} />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Compliance() {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Compliance Reports</h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>
            Control coverage across CIS, SOC 2, ISO 27001, and NIST CSF
          </p>
        </div>
      </div>

      {/* Sub-nav */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: '1px solid var(--border)', paddingBottom: 0, flexWrap: 'wrap' }}>
        {TABS.map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 14px',
              fontSize: '0.8125rem', fontWeight: tab === id ? 600 : 400,
              color: tab === id ? 'var(--accent)' : 'var(--text-muted)',
              background: 'none', border: 'none', cursor: 'pointer',
              borderBottom: tab === id ? '2px solid var(--accent)' : '2px solid transparent',
              marginBottom: -1,
              transition: 'color 0.15s',
            }}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && <OverviewTab />}
      {tab === 'frameworks' && <FrameworksTab />}
      {tab === 'reports' && <ReportBuilder />}
      {tab === 'ai' && (
        <div style={{ maxWidth: 740 }}>
          <AIChatPanel />
        </div>
      )}
      {tab === 'remediation' && <RemediationList />}
      {tab === 'trends' && <TrendChart />}
    </div>
  )
}
