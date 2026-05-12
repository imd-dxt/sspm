import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X, ChevronLeft, Loader2, CheckCircle } from 'lucide-react'
import { useCreateConnector } from '../../api/connectors'
import { cn, PLATFORMS } from '../../lib/utils'

interface Props {
  open: boolean
  onClose: () => void
}

type PlatformKey = 'github' | 'jira' | 'salesforce' | 'entraid'

interface FieldDef {
  key: string
  label: string
  placeholder?: string
  type?: 'text' | 'password'
  isConfig?: boolean
}

const PLATFORM_FIELDS: Record<PlatformKey, FieldDef[]> = {
  github: [
    { key: 'token', label: 'API Token', placeholder: 'ghp_...', type: 'password' },
    { key: 'org', label: 'GitHub Organization', placeholder: 'my-org' },
  ],
  jira: [
    { key: 'email', label: 'Account Email', placeholder: 'you@company.com' },
    { key: 'api_token', label: 'API Token', placeholder: 'ATATT...', type: 'password' },
    { key: 'domain', label: 'Jira Domain', placeholder: 'mycompany.atlassian.net', isConfig: true },
  ],
  salesforce: [
    { key: 'username', label: 'Username', placeholder: 'admin@company.com' },
    { key: 'password', label: 'Password', type: 'password' },
    { key: 'security_token', label: 'Security Token', type: 'password' },
    { key: 'instance', label: 'Instance URL', placeholder: 'mycompany.my.salesforce.com', isConfig: true },
  ],
  entraid: [
    { key: 'tenant_id', label: 'Tenant ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', isConfig: true },
    { key: 'client_id', label: 'Client ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    { key: 'client_secret', label: 'Client Secret', type: 'password' },
  ],
}

export default function AddConnectorModal({ open, onClose }: Props) {
  const [step, setStep] = useState<1 | 2>(1)
  const [selectedPlatform, setSelectedPlatform] = useState<PlatformKey | null>(null)
  const [displayName, setDisplayName] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const createConnector = useCreateConnector()

  useEffect(() => {
    if (!open) {
      // Reset on close
      setTimeout(() => {
        setStep(1)
        setSelectedPlatform(null)
        setDisplayName('')
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

  function selectPlatform(p: PlatformKey) {
    setSelectedPlatform(p)
    setDisplayName(PLATFORMS[p].label)
    setFields({})
    setApiError(null)
    setStep(2)
  }

  function setField(key: string, value: string) {
    setFields((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedPlatform) return
    setApiError(null)

    const fieldDefs = PLATFORM_FIELDS[selectedPlatform]
    const credentials: Record<string, string> = {}
    const config: Record<string, unknown> = {}

    for (const def of fieldDefs) {
      const val = fields[def.key] ?? ''
      if (def.isConfig) {
        config[def.key] = val
      } else {
        credentials[def.key] = val
      }
    }

    try {
      await createConnector.mutateAsync({
        platform_name: selectedPlatform,
        display_name: displayName || PLATFORMS[selectedPlatform].label,
        credentials,
        config,
      })
      setSuccess(true)
      setTimeout(() => {
        onClose()
      }, 1200)
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Failed to add connector')
    }
  }

  if (!open) return null

  const content = (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50"
        style={{ background: 'var(--drawer-overlay-bg)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border shadow-2xl"
        style={{ background: 'var(--surface)' }}
        role="dialog"
        aria-modal="true"
        aria-label="Add connector"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            {step === 2 && (
              <button
                onClick={() => { setStep(1); setApiError(null) }}
                className="btn-ghost -ml-2 p-1.5"
                aria-label="Back"
              >
                <ChevronLeft size={16} />
              </button>
            )}
            <h2 className="text-base font-semibold text-text">
              {step === 1 ? 'Add Connector' : `Configure ${selectedPlatform ? PLATFORMS[selectedPlatform].label : ''}`}
            </h2>
          </div>
          <button onClick={onClose} className="btn-ghost p-1.5" aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex gap-1.5 px-6 pt-4">
          {[1, 2].map((s) => (
            <div
              key={s}
              className={cn(
                'h-1 flex-1 rounded-full transition-colors',
                s <= step ? 'opacity-100' : 'opacity-20',
              )}
              style={{ background: s <= step ? 'var(--accent)' : 'var(--border)' }}
            />
          ))}
        </div>

        {/* Success state */}
        {success ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <CheckCircle size={40} style={{ color: 'var(--conn-ok)' }} />
            <p className="text-base font-semibold text-text">Connector added!</p>
            <p className="text-sm text-muted">Redirecting...</p>
          </div>
        ) : step === 1 ? (
          /* Step 1: Platform picker */
          <div className="p-6">
            <p className="mb-4 text-sm text-muted">Select the platform you want to connect.</p>
            <div className="grid grid-cols-2 gap-3">
              {(Object.entries(PLATFORMS) as [PlatformKey, typeof PLATFORMS[PlatformKey]][]).map(
                ([key, platform]) => (
                  <button
                    key={key}
                    onClick={() => selectPlatform(key)}
                    className={cn(
                      'flex flex-col gap-2 rounded-xl border p-4 text-left transition-all hover:bg-surface-2',
                      selectedPlatform === key
                        ? 'border-accent bg-accent/5'
                        : 'border-border',
                    )}
                    style={selectedPlatform === key ? { borderColor: 'var(--accent)' } : undefined}
                  >
                    <div
                      className="flex h-9 w-9 items-center justify-center rounded-lg font-mono text-xs font-bold text-white"
                      style={{ background: 'var(--accent)' }}
                    >
                      {platform.abbr}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-text">{platform.label}</p>
                      <p className="text-xs text-muted">{platform.kind}</p>
                    </div>
                  </button>
                ),
              )}
            </div>
          </div>
        ) : (
          /* Step 2: Configuration form */
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            <div>
              <label className="label" htmlFor="display-name">
                Display name
              </label>
              <input
                id="display-name"
                type="text"
                className="input"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="My GitHub Connector"
                required
              />
            </div>

            {selectedPlatform &&
              PLATFORM_FIELDS[selectedPlatform].map((field) => (
                <div key={field.key}>
                  <label className="label" htmlFor={`field-${field.key}`}>
                    {field.label}
                    {field.isConfig && (
                      <span className="ml-1 text-muted normal-case font-normal">(config)</span>
                    )}
                  </label>
                  <input
                    id={`field-${field.key}`}
                    type={field.type ?? 'text'}
                    className="input font-mono"
                    value={fields[field.key] ?? ''}
                    onChange={(e) => setField(field.key, e.target.value)}
                    placeholder={field.placeholder}
                    required
                    autoComplete={field.type === 'password' ? 'current-password' : 'off'}
                  />
                </div>
              ))}

            {apiError && (
              <div className="rounded-lg border border-sev-critical/30 bg-sev-critical/10 p-3 text-sm text-sev-critical">
                {apiError}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => { setStep(1); setApiError(null) }}
                className="btn-ghost"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={createConnector.isPending}
                className="btn-primary"
              >
                {createConnector.isPending && (
                  <Loader2 size={14} className="animate-spin" />
                )}
                Add Connector
              </button>
            </div>
          </form>
        )}
      </div>
    </>
  )

  return createPortal(content, document.body)
}
