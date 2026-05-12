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
import { useUpdateFindingStatus } from '../../api/findings'
import SeverityBadge from './SeverityBadge'
import {
  cn,
  formatRelative,
  formatAbsolute,
  platformLabel,
  statusBg,
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

export default function FindingDrawer({ finding, onClose }: Readonly<Props>) {
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [newStatus, setNewStatus] = useState<FindingStatus>('open')
  const [justification, setJustification] = useState('')
  const drawerRef = useRef<HTMLDivElement>(null)

  const updateStatus = useUpdateFindingStatus()

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
      // Prevent body scroll when drawer is open
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [finding])

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

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-30"
        style={{ background: 'var(--drawer-overlay-bg)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div
        ref={drawerRef}
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-xl flex-col"
        style={{
          background: 'var(--drawer-bg)',
          borderLeft: '2px solid #0ea5e9',
          boxShadow: '-12px 0 40px rgba(14,165,233,0.12), -4px 0 16px rgba(0,0,0,0.18)',
        }}
      >
        {/* Header */}
        <div className="flex items-start justify-between border-b border-border p-5">
          <div className="flex-1 min-w-0 pr-4">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <SeverityBadge severity={finding.severity} />
              <span
                className={cn(
                  'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium',
                  statusBg(finding.status),
                )}
              >
                {statusLabel(finding.status)}
              </span>
              <span className="text-xs font-mono text-muted bg-surface-2 px-1.5 py-0.5 rounded">
                {finding.platform}
              </span>
            </div>
            <h2 className="text-base font-semibold text-text leading-snug">
              {finding.rule_name ?? finding.rule_id}
            </h2>
            <p className="mt-0.5 text-xs font-mono text-muted truncate">{finding.resource_identifier}</p>
          </div>
          <button onClick={onClose} className="btn-ghost -mr-1 -mt-1 p-2" aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Description */}
          <section>
            <p className="label">Description</p>
            <p className="text-sm text-text">{finding.description}</p>
          </section>

          {/* Metadata grid */}
          <section className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <div>
              <p className="label">Category</p>
              <p className="text-text capitalize">{finding.category}</p>
            </div>
            <div>
              <p className="label">Platform</p>
              <p className="text-text">{platformLabel(finding.platform)}</p>
            </div>
            {finding.resource_type && (
              <div>
                <p className="label">Resource type</p>
                <p className="text-text">{finding.resource_type}</p>
              </div>
            )}
            <div className="col-span-2">
              <p className="label">Resource</p>
              <p className="font-mono text-xs text-text bg-surface-2 px-2 py-1 rounded break-all">
                {finding.resource_identifier}
              </p>
            </div>
            <div>
              <p className="label">First detected</p>
              <p className="text-text tabular-nums">{formatAbsolute(finding.first_detected)}</p>
            </div>
            <div>
              <p className="label">Last detected</p>
              <p className="text-text tabular-nums">{formatRelative(finding.last_detected)}</p>
            </div>
            {finding.connector_name && (
              <div>
                <p className="label">Connector</p>
                <p className="text-text">{finding.connector_name}</p>
              </div>
            )}
            {finding.resolved_at && (
              <div>
                <p className="label">Resolved at</p>
                <p className="text-text tabular-nums">{formatAbsolute(finding.resolved_at)}</p>
              </div>
            )}
          </section>

          {/* Impact explanation (Ollama posture analysis) */}
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
              <p className="text-sm text-text">{finding.impact_explanation}</p>
            </section>
          )}

          {/* Remediation — prefer AI-generated, fall back to static */}
          {(finding.generated_remediation || finding.remediation) && (
            <section>
              <p className="label">
                Remediation
                {finding.remediation_source === 'ollama' && (
                  <span style={{ fontWeight: 400, color: 'var(--accent)', marginLeft: 6, textTransform: 'none', fontSize: '0.6875rem' }}>
                    ✦ AI-generated
                  </span>
                )}
              </p>
              <p className="text-sm text-text" style={{ whiteSpace: 'pre-line' }}>
                {finding.generated_remediation || finding.remediation}
              </p>
              {finding.generated_remediation && finding.remediation && finding.remediation !== finding.generated_remediation && (
                <details style={{ marginTop: 8 }}>
                  <summary className="text-xs text-muted cursor-pointer" style={{ userSelect: 'none' }}>
                    Show static remediation
                  </summary>
                  <p className="text-sm text-muted mt-2" style={{ whiteSpace: 'pre-line' }}>{finding.remediation}</p>
                </details>
              )}
            </section>
          )}

          {/* Justification */}
          {finding.justification && (
            <section>
              <p className="label">Justification</p>
              <p className="text-sm text-muted italic">"{finding.justification}"</p>
            </section>
          )}

          {/* Compliance */}
          {finding.compliance_mapping.length > 0 && (
            <section>
              <p className="label">Compliance mapping</p>
              <div className="flex flex-wrap gap-1.5">
                {finding.compliance_mapping.map((c) => (
                  <span
                    key={c}
                    className="rounded bg-surface-2 px-2 py-0.5 text-xs font-mono text-muted"
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
              <pre className="overflow-x-auto rounded-lg bg-surface-2 p-3 text-xs font-mono text-muted whitespace-pre-wrap break-words">
                {JSON.stringify(finding.evidence, null, 2)}
              </pre>
            </section>
          )}
        </div>

        {/* Footer: status controls */}
        <div className="border-t border-border p-4">
          <p className="label mb-2">Change status</p>
          <div className="flex flex-wrap gap-2">
            {STATUS_OPTIONS.filter((opt) => opt.value !== finding.status).map((opt) => (
              <button
                key={opt.value}
                onClick={() => openStatusModal(opt.value)}
                className="btn-ghost border border-border"
              >
                {opt.icon}
                {opt.label}
                <ChevronDown size={12} className="ml-auto opacity-50" />
              </button>
            ))}
          </div>
          {updateStatus.isError && (
            <p className="mt-2 text-xs text-sev-critical">
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
            className="fixed inset-0 z-50"
            style={{ background: 'rgba(0,0,0,0.45)' }}
            onClick={() => setShowStatusModal(false)}
            aria-hidden="true"
          />
          <div
            className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border p-6 shadow-2xl"
            style={{ background: 'var(--surface)' }}
          >
            <h3 className="text-base font-semibold text-text mb-1">Change status</h3>
            <p className="text-sm text-muted mb-4">
              Mark this finding as{' '}
              <strong className="text-text">{statusLabel(newStatus)}</strong>
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
              className="input min-h-[80px] resize-y"
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

            <div className="mt-4 flex justify-end gap-2">
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
                {updateStatus.isPending && <Loader2 size={14} className="animate-spin" />}
                Confirm
              </button>
            </div>
          </div>
        </>
      )}
    </>
  )
}
