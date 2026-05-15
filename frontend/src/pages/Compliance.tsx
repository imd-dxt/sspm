import { useState } from 'react'
import { ShieldCheck, ChevronDown, ChevronRight, CheckCircle2, XCircle, HelpCircle, AlertTriangle } from 'lucide-react'
import { useComplianceReport, type ComplianceStandard, type ComplianceControl } from '../api/compliance'
import { formatRelative } from '../lib/utils'

// ── Score ring ────────────────────────────────────────────────────────────────
function ScoreRing({ score, size = 72 }: Readonly<{ score: number; size?: number }>) {
  const r = (size / 2) * 0.72
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - score / 100)
  const color = score >= 80 ? 'var(--ok)' : score >= 60 ? 'var(--sev-medium)' : score >= 40 ? 'var(--sev-high)' : 'var(--sev-critical)'
  return (
    <svg width={size} height={size} style={{ flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke="color-mix(in oklch, var(--border) 140%, transparent)" strokeWidth={5} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={5}
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 0.6s ease' }}
      />
      <text x={size / 2} y={size / 2 + 1} textAnchor="middle" dominantBaseline="middle"
        style={{ fill: color, fontSize: size * 0.22, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
        {score}%
      </text>
    </svg>
  )
}

// ── Status icon ───────────────────────────────────────────────────────────────
function StatusIcon({ status }: Readonly<{ status: string }>) {
  if (status === 'pass') return <CheckCircle2 size={14} style={{ color: 'var(--ok)', flexShrink: 0 }} />
  if (status === 'fail') return <XCircle size={14} style={{ color: 'var(--sev-critical)', flexShrink: 0 }} />
  return <HelpCircle size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
}

// ── Control row ───────────────────────────────────────────────────────────────
function ControlRow({ control }: Readonly<{ control: ComplianceControl }>) {
  const statusBg = control.status === 'pass'
    ? 'color-mix(in oklch, var(--ok) 10%, transparent)'
    : control.status === 'fail'
    ? 'color-mix(in oklch, var(--sev-critical) 10%, transparent)'
    : 'color-mix(in oklch, var(--border) 60%, transparent)'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 12px', borderRadius: 8,
      background: statusBg,
    }}>
      <StatusIcon status={control.status} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {control.name}
        </p>
        <p style={{ fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: 1 }}>
          {control.id}
        </p>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        {control.open_findings > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <AlertTriangle size={11} style={{ color: 'var(--sev-critical)' }} />
            <span style={{ fontSize: '0.6875rem', color: 'var(--sev-critical)', fontWeight: 600 }}>
              {control.open_findings} open
            </span>
          </div>
        )}
        <span style={{
          fontSize: '0.625rem', fontWeight: 700, padding: '2px 7px', borderRadius: 10, textTransform: 'uppercase',
          background: control.status === 'pass'
            ? 'color-mix(in oklch, var(--ok) 18%, transparent)'
            : control.status === 'fail'
            ? 'color-mix(in oklch, var(--sev-critical) 18%, transparent)'
            : 'color-mix(in oklch, var(--border) 100%, transparent)',
          color: control.status === 'pass' ? 'var(--ok)' : control.status === 'fail' ? 'var(--sev-critical)' : 'var(--text-muted)',
        }}>
          {control.status}
        </span>
      </div>
    </div>
  )
}

// ── Standard card ─────────────────────────────────────────────────────────────
function StandardCard({ standard }: Readonly<{ standard: ComplianceStandard }>) {
  const [expanded, setExpanded] = useState(false)
  const hasControls = standard.total_controls > 0
  const scoreColor = standard.score >= 80 ? 'var(--ok)'
    : standard.score >= 60 ? 'var(--sev-medium)'
    : standard.score >= 40 ? 'var(--sev-high)'
    : 'var(--sev-critical)'

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* Card header */}
      <div style={{ padding: '20px 24px', display: 'flex', alignItems: 'center', gap: 20 }}>
        <ScoreRing score={standard.score} size={80} />

        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>
            {standard.name}
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{standard.description}</p>

          {hasControls && (
            <div style={{ display: 'flex', gap: 16, marginTop: 10, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <CheckCircle2 size={13} style={{ color: 'var(--ok)' }} />
                <span style={{ fontSize: '0.75rem', color: 'var(--text)' }}>
                  <strong style={{ fontVariantNumeric: 'tabular-nums' }}>{standard.passing_controls}</strong>
                  <span style={{ color: 'var(--text-muted)' }}> passing</span>
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <XCircle size={13} style={{ color: 'var(--sev-critical)' }} />
                <span style={{ fontSize: '0.75rem', color: 'var(--text)' }}>
                  <strong style={{ fontVariantNumeric: 'tabular-nums' }}>{standard.failing_controls}</strong>
                  <span style={{ color: 'var(--text-muted)' }}> failing</span>
                </span>
              </div>
              {standard.unknown_controls > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <HelpCircle size={13} style={{ color: 'var(--text-muted)' }} />
                  <span style={{ fontSize: '0.75rem', color: 'var(--text)' }}>
                    <strong>{standard.unknown_controls}</strong>
                    <span style={{ color: 'var(--text-muted)' }}> not tested</span>
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8, flexShrink: 0 }}>
          <span style={{
            fontSize: '1.125rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
            color: scoreColor,
          }}>
            {standard.score}%
          </span>
          {hasControls && (
            <button
              onClick={() => setExpanded((e) => !e)}
              className="btn-ghost"
              style={{ fontSize: '0.75rem', gap: 4 }}
            >
              {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              {expanded ? 'Hide' : 'Details'}
            </button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {hasControls && (
        <div style={{ height: 4, background: 'var(--border)', margin: '0 24px', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%', borderRadius: 2, transition: 'width 0.6s ease',
            width: `${standard.score}%`,
            background: scoreColor,
          }} />
        </div>
      )}

      {/* Controls list */}
      {expanded && hasControls && (
        <div style={{ padding: '16px 24px 20px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <p style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
            Controls · {standard.total_controls} total
          </p>
          {standard.controls.map((c) => (
            <ControlRow key={c.id} control={c} />
          ))}
        </div>
      )}

      {!hasControls && (
        <div style={{ padding: '0 24px 20px' }}>
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            No rules mapped to this standard yet.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Overall summary strip ─────────────────────────────────────────────────────
function OverallSummary({ score, standards }: Readonly<{ score: number; standards: ComplianceStandard[] }>) {
  const totalControls = standards.reduce((s, x) => s + x.total_controls, 0)
  const totalPassing = standards.reduce((s, x) => s + x.passing_controls, 0)
  const totalFailing = standards.reduce((s, x) => s + x.failing_controls, 0)
  const scoreColor = score >= 80 ? 'var(--ok)' : score >= 60 ? 'var(--sev-medium)' : score >= 40 ? 'var(--sev-high)' : 'var(--sev-critical)'

  return (
    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center', padding: '16px 20px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <ScoreRing score={score} size={64} />
        <div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Overall Compliance</p>
          <p style={{ fontSize: '1.5rem', fontWeight: 700, color: scoreColor, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{score}%</p>
        </div>
      </div>
      <div style={{ width: 1, background: 'var(--border)', alignSelf: 'stretch', flexShrink: 0 }} />
      <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
        {[
          { label: 'Standards', value: standards.length, color: 'var(--text)' },
          { label: 'Controls', value: totalControls, color: 'var(--text)' },
          { label: 'Passing', value: totalPassing, color: 'var(--ok)' },
          { label: 'Failing', value: totalFailing, color: 'var(--sev-critical)' },
        ].map(({ label, value, color }) => (
          <div key={label}>
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginBottom: 2 }}>{label}</p>
            <p style={{ fontSize: '1.25rem', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function Compliance() {
  const { data, isLoading, error } = useComplianceReport()

  if (isLoading) {
    return (
      <div>
        <div className="page-header">
          <div>
            <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Compliance Reports</h2>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>Control coverage across CIS, SOC 2, ISO 27001, and NIST CSF</p>
          </div>
        </div>
        <div style={{ height: 80, borderRadius: 12, marginBottom: 24 }} className="skeleton" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(420px, 1fr))', gap: 20 }}>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton" style={{ height: 180, borderRadius: 12 }} />
          ))}
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div>
        <div className="page-header">
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Compliance Reports</h2>
        </div>
        <div className="card" style={{ padding: 32, textAlign: 'center' }}>
          <ShieldCheck size={32} style={{ color: 'var(--text-muted)', margin: '0 auto 12px' }} />
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Unable to load compliance data. Check that rules are loaded and connectors have synced.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Compliance Reports</h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>
            Control coverage across CIS, SOC 2, ISO 27001, and NIST CSF
            {data.last_updated && (
              <span style={{ marginLeft: 6 }}>· updated {formatRelative(data.last_updated)}</span>
            )}
          </p>
        </div>
      </div>

      <OverallSummary score={data.overall_score} standards={data.standards} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(460px, 1fr))', gap: 20 }}>
        {data.standards.map((std) => (
          <StandardCard key={std.id} standard={std} />
        ))}
      </div>
    </div>
  )
}
