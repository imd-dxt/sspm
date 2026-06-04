import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X, Loader2, KeyRound } from 'lucide-react'
import { useUpdateConnectorCredentials } from '../../api/connectors'
import { getCredentialFields } from '../../lib/connectorFields'

interface Props {
  open: boolean
  onClose: () => void
  connectorId: string
  platform: string
  displayName: string
}

export default function UpdateCredentialsModal({
  open, onClose, connectorId, platform, displayName,
}: Readonly<Props>) {
  const [fields, setFields] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const mutation = useUpdateConnectorCredentials()

  const credentialFields = getCredentialFields(platform)

  useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setFields({})
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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setApiError(null)
    const allFilled = credentialFields.every((f) => fields[f.key]?.trim())
    if (!allFilled) {
      setApiError('All credential fields are required.')
      return
    }
    mutation.mutate(
      { id: connectorId, credentials: fields },
      {
        onSuccess: () => {
          setSuccess(true)
          setTimeout(() => onClose(), 1200)
        },
        onError: (err) => {
          setApiError(err instanceof Error ? err.message : 'Failed to update credentials.')
        },
      },
    )
  }

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 60,
          background: 'rgba(0,0,0,0.45)',
        }}
        aria-hidden="true"
      />

      {/* Modal */}
      <div style={{
        position: 'fixed', zIndex: 61,
        left: '50%', top: '50%', transform: 'translate(-50%, -50%)',
        width: '100%', maxWidth: 460,
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 16, padding: 24,
        boxShadow: '0 24px 64px rgba(0,0,0,0.22)',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8,
            background: 'color-mix(in oklch, var(--accent) 12%, transparent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <KeyRound size={16} style={{ color: 'var(--accent)' }} />
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)' }}>
              Rotate credentials
            </h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
              {displayName} · {platform}
            </p>
          </div>
          <button onClick={onClose} className="btn-ghost" style={{ padding: 6 }} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {success ? (
          <div style={{
            padding: '20px 16px', borderRadius: 10, textAlign: 'center',
            background: 'color-mix(in oklch, var(--ok) 10%, transparent)',
            border: '1px solid color-mix(in oklch, var(--ok) 25%, transparent)',
          }}>
            <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--ok)' }}>
              Credentials updated ✓
            </p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Click "Test" on the connector to verify the new token works.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {credentialFields.length === 0 ? (
              <p style={{ fontSize: '0.875rem', color: 'var(--sev-critical)' }}>
                Unknown platform "{platform}" — cannot rotate credentials here.
              </p>
            ) : credentialFields.map((f) => (
              <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                  {f.label}
                </label>
                <input
                  type={f.type === 'password' ? 'password' : 'text'}
                  value={fields[f.key] ?? ''}
                  onChange={(e) => setFields((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  autoComplete="off"
                  disabled={mutation.isPending}
                  style={{
                    padding: '9px 12px', borderRadius: 8, fontSize: '0.875rem',
                    border: '1px solid var(--border)', background: 'var(--surface-2)',
                    color: 'var(--text)', outline: 'none', width: '100%', boxSizing: 'border-box',
                  }}
                />
                {f.hint && (
                  <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>{f.hint}</p>
                )}
              </div>
            ))}

            {apiError && (
              <p style={{
                fontSize: '0.75rem', color: 'var(--sev-critical)',
                background: 'color-mix(in oklch, var(--sev-critical) 8%, transparent)',
                padding: '8px 10px', borderRadius: 8, margin: 0,
              }}>
                {apiError}
              </p>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
              <button type="button" onClick={onClose} className="btn-ghost">Cancel</button>
              <button
                type="submit"
                disabled={mutation.isPending || credentialFields.length === 0}
                className="btn-primary"
              >
                {mutation.isPending && <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />}
                Save & encrypt
              </button>
            </div>
          </form>
        )}
      </div>
    </>,
    document.body,
  )
}
