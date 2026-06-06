import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X, Loader2, ShieldPlus, Plus } from 'lucide-react'
import { useCreateCustomPolicy, type CustomPolicyCreate } from '../../api/rules'

interface Props {
  open: boolean
  onClose: () => void
}

const DEFAULTS: CustomPolicyCreate = {
  name: '',
  platform: 'github',
  severity: 'medium',
  category: 'custom',
  description: '',
  remediation: '',
  referentials: [],
  compliance_mapping: [],
  detection_query: '',
}

const PLATFORMS: CustomPolicyCreate['platform'][] = [
  'github', 'jira', 'salesforce', 'entraid', 'cross-platform',
]
const SEVERITIES: CustomPolicyCreate['severity'][] = ['critical', 'high', 'medium', 'low', 'info']
const FRAMEWORKS = ['CIS', 'SOC2', 'ISO27001', 'NIST-CSF']

export default function CustomPolicyModal({ open, onClose }: Readonly<Props>) {
  const [draft, setDraft] = useState<CustomPolicyCreate>(DEFAULTS)
  const [advanced, setAdvanced] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const create = useCreateCustomPolicy()

  useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setDraft(DEFAULTS)
        setAdvanced(false)
        setApiError(null)
        setSuccess(false)
      }, 200)
    }
  }, [open])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    if (open) document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  function toggleFramework(fw: string) {
    setDraft((prev) => ({
      ...prev,
      referentials: prev.referentials.includes(fw)
        ? prev.referentials.filter((f) => f !== fw)
        : [...prev.referentials, fw],
    }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setApiError(null)
    if (!draft.name.trim() || draft.name.trim().length < 3) {
      setApiError('Policy name must be at least 3 characters.')
      return
    }
    create.mutate(draft, {
      onSuccess: () => {
        setSuccess(true)
        setTimeout(() => onClose(), 1200)
      },
      onError: (err) => setApiError(err instanceof Error ? err.message : 'Failed to create policy.'),
    })
  }

  return createPortal(
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,0.45)' }}
        aria-hidden="true"
      />

      <div style={{
        position: 'fixed', zIndex: 61,
        left: '50%', top: '50%', transform: 'translate(-50%, -50%)',
        width: '100%', maxWidth: 600, maxHeight: '90vh',
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, boxShadow: '0 24px 64px rgba(0,0,0,0.22)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '18px 22px', borderBottom: '1px solid var(--border)',
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'color-mix(in oklch, var(--accent) 12%, transparent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <ShieldPlus size={16} style={{ color: 'var(--accent)' }} />
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)' }}>
              Custom Policy
            </h3>
            <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2 }}>
              Encode an org-specific rule tailored to your risk appetite
            </p>
          </div>
          <button onClick={onClose} className="btn-ghost" style={{ padding: 6 }} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '18px 22px', overflowY: 'auto', flex: 1 }}>
          {success ? (
            <div style={{
              padding: '20px 16px', borderRadius: 10, textAlign: 'center',
              background: 'color-mix(in oklch, var(--ok) 10%, transparent)',
              border: '1px solid color-mix(in oklch, var(--ok) 25%, transparent)',
            }}>
              <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--ok)' }}>
                Custom policy created ✓
              </p>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                It is now active and will contribute to your compliance score.
              </p>
            </div>
          ) : (
            <form id="custom-policy-form" onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <Field label="Policy name" hint="A concise, recognisable label for this rule.">
                <input
                  type="text" value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  placeholder="e.g. No public repos with the word 'production'"
                  style={inputStyle} required
                />
              </Field>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <Field label="Platform">
                  <select
                    value={draft.platform}
                    onChange={(e) => setDraft({ ...draft, platform: e.target.value as CustomPolicyCreate['platform'] })}
                    style={inputStyle}
                  >
                    {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </Field>
                <Field label="Severity">
                  <select
                    value={draft.severity}
                    onChange={(e) => setDraft({ ...draft, severity: e.target.value as CustomPolicyCreate['severity'] })}
                    style={inputStyle}
                  >
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </Field>
              </div>

              <Field label="Category" hint="Short tag for grouping (e.g. branch-protection, data-loss).">
                <input
                  type="text" value={draft.category}
                  onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                  placeholder="custom" style={inputStyle}
                />
              </Field>

              <Field label="Description" hint="What does this policy detect and why does it matter for your org?">
                <textarea
                  value={draft.description}
                  onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  rows={3} style={{ ...inputStyle, minHeight: 60, resize: 'vertical' }}
                  placeholder="Detect repositories named *production* that are publicly accessible — these expose our most sensitive code."
                />
              </Field>

              <Field label="Remediation steps" hint="How should someone fix a finding from this policy?">
                <textarea
                  value={draft.remediation}
                  onChange={(e) => setDraft({ ...draft, remediation: e.target.value })}
                  rows={2} style={{ ...inputStyle, minHeight: 50, resize: 'vertical' }}
                  placeholder="Set the repository visibility to 'private' or rename it to not contain 'production'."
                />
              </Field>

              <Field label="Contributes to frameworks" hint="Which compliance frameworks' scores should this policy count toward?">
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {FRAMEWORKS.map((fw) => {
                    const active = draft.referentials.includes(fw)
                    return (
                      <button
                        key={fw} type="button" onClick={() => toggleFramework(fw)}
                        style={{
                          padding: '5px 10px', borderRadius: 6, cursor: 'pointer',
                          fontSize: '0.75rem', fontWeight: 600,
                          border: '1px solid ' + (active ? 'var(--accent)' : 'var(--border)'),
                          background: active ? 'color-mix(in oklch, var(--accent) 14%, transparent)' : 'var(--surface-2)',
                          color: active ? 'var(--accent)' : 'var(--text-muted)',
                        }}
                      >{fw}</button>
                    )
                  })}
                </div>
              </Field>

              <button
                type="button"
                onClick={() => setAdvanced((v) => !v)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', fontSize: '0.75rem',
                  padding: 0, textAlign: 'left',
                  display: 'flex', alignItems: 'center', gap: 4,
                }}
              >
                {advanced ? '▾' : '▸'} Advanced: write a Cypher detection query
              </button>

              {advanced && (
                <Field label="Cypher detection query" hint="Leave empty for a documentation-only policy. The query should RETURN one row per violation with a resource identifier.">
                  <textarea
                    value={draft.detection_query}
                    onChange={(e) => setDraft({ ...draft, detection_query: e.target.value })}
                    rows={6}
                    style={{
                      ...inputStyle, minHeight: 110,
                      fontFamily: 'ui-monospace, SFMono-Regular, monospace',
                      fontSize: '0.75rem', resize: 'vertical',
                    }}
                    placeholder={`MATCH (r:Resource {platform:'github', resource_subtype:'repository'})\nWHERE r.visibility='public' AND r.name CONTAINS 'production'\nRETURN r.name AS resource_id, r.name AS resource_name`}
                  />
                </Field>
              )}

              {apiError && (
                <p style={{
                  fontSize: '0.75rem', color: 'var(--sev-critical)',
                  background: 'color-mix(in oklch, var(--sev-critical) 8%, transparent)',
                  padding: '8px 10px', borderRadius: 8, margin: 0,
                }}>
                  {apiError}
                </p>
              )}
            </form>
          )}
        </div>

        {/* Footer */}
        {!success && (
          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 8,
            padding: '14px 22px', borderTop: '1px solid var(--border)',
          }}>
            <button onClick={onClose} className="btn-ghost">Cancel</button>
            <button
              type="submit" form="custom-policy-form"
              disabled={create.isPending || !draft.name.trim()}
              className="btn-primary"
              style={{ opacity: create.isPending || !draft.name.trim() ? 0.5 : 1 }}
            >
              {create.isPending
                ? <><Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Creating…</>
                : <><Plus size={12} /> Create policy</>}
            </button>
          </div>
        )}
      </div>
    </>,
    document.body,
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  padding: '8px 12px', borderRadius: 8, fontSize: '0.8125rem',
  border: '1px solid var(--border)', background: 'var(--surface-2)',
  color: 'var(--text)', outline: 'none', width: '100%', boxSizing: 'border-box',
}

function Field({
  label, hint, children,
}: Readonly<{ label: string; hint?: string; children: React.ReactNode }>) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>{label}</label>
      {hint && <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: -2 }}>{hint}</p>}
      <div style={{ marginTop: 2 }}>{children}</div>
    </div>
  )
}
