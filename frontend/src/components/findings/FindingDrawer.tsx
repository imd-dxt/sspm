import { useState, useEffect, useRef } from 'react'
import {
  X,
  ChevronDown,
  Clock,
  Shield,
  AlertTriangle,
  CheckCircle,
  Loader2,
} from 'lucide-react'
import type { Finding } from '../../api/types'
import { useUpdateFindingStatus, useRemediateFinding, useCiaImpact, type CiaImpact } from '../../api/findings'
import SeverityBadge from './SeverityBadge'
import {
  formatRelative,
  formatAbsolute,
  platformLabel,
  statusLabel,
} from '../../lib/utils'

interface Props {
  finding: Finding | null
  onClose: () => void
}

const STATUS_OPTIONS = [
  { value: 'open', label: 'Open', icon: <AlertTriangle size={14} /> },
  { value: 'resolved', label: 'Resolved', icon: <CheckCircle size={14} /> },
  { value: 'false_positive', label: 'False positive', icon: <Shield size={14} /> },
  { value: 'accepted_risk', label: 'Accepted risk', icon: <Clock size={14} /> },
] as const

type FindingStatus = 'open' | 'resolved' | 'false_positive' | 'accepted_risk'

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  open:           { bg: 'color-mix(in oklch, var(--sev-high) 15%, transparent)',     color: 'var(--sev-high)' },
  resolved:       { bg: 'color-mix(in oklch, var(--sev-ok) 15%, transparent)',       color: 'var(--sev-ok)' },
  false_positive: { bg: 'color-mix(in oklch, var(--text-muted) 15%, transparent)',   color: 'var(--text-muted)' },
  accepted_risk:  { bg: 'color-mix(in oklch, var(--sev-medium) 15%, transparent)',   color: 'var(--sev-medium)' },
}

export default function FindingDrawer({ finding, onClose }: Readonly<Props>) {
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [newStatus, setNewStatus] = useState<FindingStatus>('open')
  const [justification, setJustification] = useState('')
  const [ciaResult, setCiaResult] = useState<CiaImpact | null>(null)
  const drawerRef = useRef<HTMLDivElement>(null)

  const updateStatus = useUpdateFindingStatus()
  const remediate = useRemediateFinding()
  const ciaImpact = useCiaImpact()

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        if (showStatusModal) setShowStatusModal(false)
        else onClose()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [showStatusModal, onClose])

  useEffect(() => {
    if (finding) {
      document.body.style.overflow = 'hidden'
      setCiaResult(null)
      // Auto-generate CIA triad analysis
      ciaImpact.mutate(finding.id, { onSuccess: (data) => setCiaResult(data) })
      // Auto-generate remediation if not yet persisted
      if (finding.status === 'open' && !finding.generated_remediation) {
        remediate.mutate(finding.id)
      }
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [finding?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!finding) return null

  function openStatusModal(status: FindingStatus) {
    setNewStatus(status)
    setJustification('')
    setShowStatusModal(true)
  }

  async function submitStatusChange() {
    if (!finding) return
    await updateStatus.mutateAsync({
      id: finding.id,
      data: {
        status: newStatus,
        justification: justification || undefined,
      },
    })
    setShowStatusModal(false)
  }

  const statusColor = STATUS_COLORS[finding.status] ?? STATUS_COLORS.open
  const complianceItems = finding.compliance_mapping ?? []

  return (
    <>
      {/* Backdrop */}
      <div
        className="drawer-overlay"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div ref={drawerRef} className="drawer">
        {/* Header */}
        <div className="drawer-header">
          <div style={{ flex: 1, minWidth: 0, paddingRight: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
              <SeverityBadge severity={finding.severity} />
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                borderRadius: 6,
                padding: '2px 8px',
                fontSize: '0.75rem',
                fontWeight: 600,
                background: statusColor.bg,
                color: statusColor.color,
              }}>
                {statusLabel(finding.status)}
              </span>
              <span style={{
                fontSize: '0.6875rem',
                fontFamily: 'monospace',
                color: 'var(--text-muted)',
                background: 'var(--surface-2)',
                padding: '2px 6px',
                borderRadius: 4,
              }}>
                {finding.platform}
              </span>
            </div>
            <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)', lineHeight: 1.35 }}>
              {finding.rule_name ?? finding.rule_id}
            </h2>
            <p style={{ marginTop: 2, fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {finding.resource_identifier}
            </p>
          </div>
          <button onClick={onClose} className="btn-ghost" style={{ marginRight: -4, marginTop: -4, padding: 8 }} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="drawer-body" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Description */}
          <section>
            <p className="label">Description</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text)' }}>{finding.description}</p>
          </section>

          {/* Metadata grid */}
          <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16, rowGap: 12, fontSize: '0.875rem' }}>
            <div>
              <p className="label">Category</p>
              <p style={{ color: 'var(--text)', textTransform: 'capitalize' }}>{finding.category}</p>
            </div>
            <div>
              <p className="label">Platform</p>
              <p style={{ color: 'var(--text)' }}>{platformLabel(finding.platform)}</p>
            </div>
            {finding.resource_type && (
              <div>
                <p className="label">Resource type</p>
                <p style={{ color: 'var(--text)' }}>{finding.resource_type}</p>
              </div>
            )}
            <div style={{ gridColumn: '1 / -1' }}>
              <p className="label">Resource</p>
              <p style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--text)', background: 'var(--surface-2)', padding: '4px 8px', borderRadius: 6, wordBreak: 'break-all' }}>
                {finding.resource_identifier}
              </p>
            </div>
            <div>
              <p className="label">First detected</p>
              <p style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{formatAbsolute(finding.first_detected)}</p>
            </div>
            <div>
              <p className="label">Last detected</p>
              <p style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{formatRelative(finding.last_detected)}</p>
            </div>
            {finding.connector_name && (
              <div>
                <p className="label">Connector</p>
                <p style={{ color: 'var(--text)' }}>{finding.connector_name}</p>
              </div>
            )}
            {finding.resolved_at && (
              <div>
                <p className="label">Resolved at</p>
                <p style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{formatAbsolute(finding.resolved_at)}</p>
              </div>
            )}
          </section>

          {/* Impact explanation */}
          {finding.impact_explanation && (
            <section style={{
              background: 'color-mix(in oklch, var(--sev-high) 8%, transparent)',
              border: '1px solid color-mix(in oklch, var(--sev-high) 25%, transparent)',
              borderRadius: 10,
              padding: '12px 14px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <AlertTriangle size={13} style={{ color: 'var(--sev-high)', flexShrink: 0 }} />
                <p className="label" style={{ marginBottom: 0 }}>
                  Potential Impact
                  {finding.impact_factor !== null && (
                    <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 6, textTransform: 'none', fontSize: '0.6875rem' }}>
                      risk factor {Math.round((finding.impact_factor ?? 0) * 100)}%
                    </span>
                  )}
                </p>
              </div>
              <p style={{ fontSize: '0.875rem', color: 'var(--text)' }}>{finding.impact_explanation}</p>
            </section>
          )}

          {/* CIA Triad Impact — auto-generated on drawer open */}
          <section>
            <p className="label" style={{ marginBottom: 6 }}>
              CIA Triad Impact
              {ciaResult?.source === 'ollama' && (
                <span style={{ fontWeight: 400, color: 'var(--accent)', marginLeft: 6, textTransform: 'none', fontSize: '0.6875rem' }}>
                  ✦ AI-generated
                </span>
              )}
            </p>
            {ciaImpact.isPending && !ciaResult ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Loader2 size={12} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>Analyzing CIA triad impact…</p>
              </div>
            ) : ciaResult ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {([
                  { key: 'confidentiality', label: 'C', title: 'Confidentiality', color: '#6366f1' },
                  { key: 'integrity',       label: 'I', title: 'Integrity',       color: '#f59e0b' },
                  { key: 'availability',    label: 'A', title: 'Availability',    color: '#22c55e' },
                ] as const).map(({ key, label, title, color }) => (
                  <div key={key} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <span style={{
                      flexShrink: 0, width: 22, height: 22, borderRadius: 6, display: 'flex',
                      alignItems: 'center', justifyContent: 'center',
                      background: `color-mix(in oklch, ${color} 15%, transparent)`,
                      color, fontSize: '0.6875rem', fontWeight: 700,
                    }}>{label}</span>
                    <div>
                      <p style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: 2 }}>{title}</p>
                      <p style={{ fontSize: '0.8125rem', color: 'var(--text)' }}>{ciaResult[key]}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </section>

          {/* Remediation — auto-generated on drawer open if not yet persisted */}
          <section>
            <p className="label" style={{ marginBottom: 6 }}>
              Remediation
              {finding.remediation_source === 'ollama' && (
                <span style={{ fontWeight: 400, color: 'var(--accent)', marginLeft: 6, textTransform: 'none', fontSize: '0.6875rem' }}>
                  ✦ AI-generated
                </span>
              )}
            </p>
            {remediate.isPending && !finding.generated_remediation ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Loader2 size={12} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>Generating AI remediation…</p>
              </div>
            ) : (finding.generated_remediation || finding.remediation) ? (
              <>
                <p style={{ fontSize: '0.875rem', color: 'var(--text)', whiteSpace: 'pre-line' }}>
                  {finding.generated_remediation || finding.remediation}
                </p>
                {finding.generated_remediation && finding.remediation && finding.remediation !== finding.generated_remediation && (
                  <details style={{ marginTop: 8 }}>
                    <summary style={{ fontSize: '0.75rem', color: 'var(--text-muted)', cursor: 'pointer', userSelect: 'none' }}>
                      Show static remediation
                    </summary>
                    <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: 8, whiteSpace: 'pre-line' }}>{finding.remediation}</p>
                  </details>
                )}
              </>
            ) : (
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                No remediation guidance available.
              </p>
            )}
          </section>

          {/* Justification */}
          {finding.justification && (
            <section>
              <p className="label">Justification</p>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>"{finding.justification}"</p>
            </section>
          )}

          {/* Compliance */}
          {complianceItems.length > 0 && (
            <section>
              <p className="label">Compliance mapping</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {complianceItems.map((c) => (
                  <span
                    key={c}
                    style={{ borderRadius: 6, background: 'var(--surface-2)', padding: '2px 8px', fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)' }}
                  >
                    {c}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Evidence */}
          {finding.evidence && Object.keys(finding.evidence).length > 0 && (
            <section>
              <p className="label">Evidence</p>
              <pre className="code-block">
                {JSON.stringify(finding.evidence, null, 2)}
              </pre>
            </section>
          )}
        </div>

        {/* Footer: status controls */}
        <div style={{ borderTop: '1px solid var(--border)', padding: '16px 20px', flexShrink: 0 }}>
          <p className="label" style={{ marginBottom: 8 }}>Change status</p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {STATUS_OPTIONS.filter((opt) => opt.value !== finding.status).map((opt) => (
              <button
                key={opt.value}
                onClick={() => openStatusModal(opt.value)}
                className="btn-ghost"
                style={{ border: '1px solid var(--border)' }}
              >
                {opt.icon}
                {opt.label}
                <ChevronDown size={12} style={{ marginLeft: 'auto', opacity: 0.5 }} />
              </button>
            ))}
          </div>
          {updateStatus.isError && (
            <p style={{ marginTop: 8, fontSize: '0.75rem', color: 'var(--sev-critical)' }}>
              Failed to update:{' '}
              {updateStatus.error instanceof Error
                ? updateStatus.error.message
                : 'Unknown error'}
            </p>
          )}
        </div>
      </div>

      {/* Status change modal */}
      {showStatusModal && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.45)' }}
            onClick={() => setShowStatusModal(false)}
            aria-hidden="true"
          />
          <div style={{
            position: 'fixed',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 61,
            width: '100%',
            maxWidth: 440,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 16,
            padding: 24,
            boxShadow: '0 24px 64px rgba(0,0,0,0.22)',
          }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>Change status</h3>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 16 }}>
              Mark this finding as{' '}
              <strong style={{ color: 'var(--text)' }}>{statusLabel(newStatus)}</strong>
            </p>

            <label className="label" htmlFor="justification-input">
              Justification
              {['false_positive', 'accepted_risk'].includes(newStatus) ? (
                <span style={{ color: 'var(--sev-critical)', marginLeft: 4 }}>*</span>
              ) : (
                <span style={{ color: 'var(--text-muted)', marginLeft: 4, fontWeight: 400, textTransform: 'none' }}>(optional)</span>
              )}
            </label>
            <textarea
              id="justification-input"
              className="input"
              style={{ minHeight: 80, resize: 'vertical' }}
              placeholder={
                ['false_positive', 'accepted_risk'].includes(newStatus)
                  ? 'Required — explain why this status is appropriate…'
                  : 'Describe why this status is appropriate…'
              }
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
            />
            {['false_positive', 'accepted_risk'].includes(newStatus) && !justification.trim() && (
              <p style={{ fontSize: '0.75rem', color: 'var(--sev-critical)', marginTop: 4 }}>
                Justification is required for this status.
              </p>
            )}

            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button onClick={() => setShowStatusModal(false)} className="btn-ghost">
                Cancel
              </button>
              <button
                onClick={submitStatusChange}
                disabled={
                  updateStatus.isPending ||
                  (['false_positive', 'accepted_risk'].includes(newStatus) && !justification.trim())
                }
                className="btn-primary"
              >
                {updateStatus.isPending && <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />}
                Confirm
              </button>
            </div>
          </div>
        </>
      )}
    </>
  )
}
