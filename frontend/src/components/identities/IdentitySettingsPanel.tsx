import { useState, useEffect } from 'react'
import { Settings, ChevronDown, ChevronRight, Loader2, X, Plus, Save, CheckCircle, ShieldCheck } from 'lucide-react'
import {
  useIdentitySettings,
  useUpdateIdentitySettings,
  type IdentitySettings,
} from '../../api/identities'

const DEFAULTS: IdentitySettings = {
  internal_email_domains: [],
  inactive_user_days:     90,
  extra_admin_roles:      [],
  flag_external_users:    true,
  alert_on_new_admin:     false,
}

export default function IdentitySettingsPanel() {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<IdentitySettings>(DEFAULTS)
  const [domainInput, setDomainInput] = useState('')
  const [roleInput, setRoleInput] = useState('')
  const [justSaved, setJustSaved] = useState(false)

  const { data, isLoading } = useIdentitySettings()
  const update = useUpdateIdentitySettings()

  // Sync server state into the form whenever it loads
  useEffect(() => {
    if (data) setDraft(data)
  }, [data])

  function addDomain() {
    const d = domainInput.trim().toLowerCase().replace(/^@/, '')
    if (!d || draft.internal_email_domains.includes(d)) return
    setDraft({ ...draft, internal_email_domains: [...draft.internal_email_domains, d] })
    setDomainInput('')
  }

  function removeDomain(d: string) {
    setDraft({ ...draft, internal_email_domains: draft.internal_email_domains.filter((x) => x !== d) })
  }

  function addRole() {
    const r = roleInput.trim().toLowerCase()
    if (!r || draft.extra_admin_roles.includes(r)) return
    setDraft({ ...draft, extra_admin_roles: [...draft.extra_admin_roles, r] })
    setRoleInput('')
  }

  function removeRole(r: string) {
    setDraft({ ...draft, extra_admin_roles: draft.extra_admin_roles.filter((x) => x !== r) })
  }

  function save() {
    update.mutate(draft, {
      onSuccess: () => {
        setJustSaved(true)
        setTimeout(() => setJustSaved(false), 1800)
      },
    })
  }

  const isDirty = data && JSON.stringify(data) !== JSON.stringify(draft)

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      {/* Collapsible header */}
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 18px', background: 'none', border: 'none', cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: 'color-mix(in oklch, var(--accent) 12%, transparent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Settings size={14} style={{ color: 'var(--accent)' }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>
            Identity settings
          </p>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 1 }}>
            Admin controls for external-user detection, admin-role mapping, and other identity heuristics
          </p>
        </div>
        {open
          ? <ChevronDown size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          : <ChevronRight size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
      </button>

      {open && (
        <div style={{ padding: '4px 18px 18px', borderTop: '1px solid var(--border)' }}>
          {isLoading ? (
            <div className="skeleton" style={{ height: 80, marginTop: 16 }} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, marginTop: 14 }}>

              {/* Internal email domains */}
              <SettingRow
                icon={<ShieldCheck size={13} />}
                title="Internal email domains"
                hint="Users whose email does NOT end in one of these domains will be flagged as external. Add domains like hps.com, acme.com — no leading @."
              >
                <TagInput
                  value={domainInput}
                  onChange={setDomainInput}
                  onAdd={addDomain}
                  placeholder="hps.com"
                />
                <TagList items={draft.internal_email_domains} onRemove={removeDomain} />
              </SettingRow>

              {/* Inactive user threshold */}
              <SettingRow
                icon={<Settings size={13} />}
                title="Flag inactive users after"
                hint="A user with no login in this many days is highlighted in the users table (informational only)."
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="number"
                    min={0}
                    max={3650}
                    value={draft.inactive_user_days}
                    onChange={(e) => setDraft({ ...draft, inactive_user_days: Number(e.target.value) || 0 })}
                    style={inputStyle}
                  />
                  <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>days</span>
                </div>
              </SettingRow>

              {/* Extra admin roles */}
              <SettingRow
                icon={<ShieldCheck size={13} />}
                title="Extra admin role names"
                hint="Additional role names to be treated as admin (case-insensitive). The built-in list already covers 'admin', 'owner', 'administrator', etc."
              >
                <TagInput
                  value={roleInput}
                  onChange={setRoleInput}
                  onAdd={addRole}
                  placeholder="superuser"
                />
                <TagList items={draft.extra_admin_roles} onRemove={removeRole} />
              </SettingRow>

              {/* Toggles */}
              <SettingRow
                icon={<Settings size={13} />}
                title="Display preferences"
                hint=""
              >
                <Toggle
                  label="Flag external users in the UI"
                  value={draft.flag_external_users}
                  onChange={(v) => setDraft({ ...draft, flag_external_users: v })}
                />
                <Toggle
                  label="Alert when a new admin account appears"
                  value={draft.alert_on_new_admin}
                  onChange={(v) => setDraft({ ...draft, alert_on_new_admin: v })}
                />
              </SettingRow>

              {/* Action row */}
              <div style={{
                display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10,
                borderTop: '1px solid var(--border)', paddingTop: 14, marginTop: 4,
              }}>
                {update.isError && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--sev-critical)' }}>
                    Could not save settings.
                  </span>
                )}
                {justSaved && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--ok)' }}>
                    <CheckCircle size={12} /> Saved
                  </span>
                )}
                <button
                  onClick={save}
                  disabled={!isDirty || update.isPending}
                  className="btn-primary btn-sm"
                  style={{ opacity: !isDirty || update.isPending ? 0.5 : 1 }}
                >
                  {update.isPending
                    ? <><Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Saving…</>
                    : <><Save size={12} /> Save changes</>}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Small helpers ────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  padding: '7px 10px', borderRadius: 7, fontSize: '0.8125rem',
  border: '1px solid var(--border)', background: 'var(--surface-2)',
  color: 'var(--text)', outline: 'none', width: 90,
  boxSizing: 'border-box',
}

function SettingRow({
  icon, title, hint, children,
}: Readonly<{ icon: React.ReactNode; title: string; hint: string; children: React.ReactNode }>) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: 'var(--text-muted)' }}>{icon}</span>
        <p style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text)' }}>{title}</p>
      </div>
      {hint && (
        <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: -2 }}>{hint}</p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
        {children}
      </div>
    </div>
  )
}

function TagInput({
  value, onChange, onAdd, placeholder,
}: Readonly<{
  value: string
  onChange: (v: string) => void
  onAdd: () => void
  placeholder: string
}>) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); onAdd() } }}
        placeholder={placeholder}
        style={{ ...inputStyle, width: 'auto', flex: 1 }}
      />
      <button
        type="button"
        onClick={onAdd}
        disabled={!value.trim()}
        className="btn-ghost btn-sm"
        style={{ border: '1px solid var(--border)' }}
      >
        <Plus size={12} /> Add
      </button>
    </div>
  )
}

function TagList({
  items, onRemove,
}: Readonly<{ items: string[]; onRemove: (item: string) => void }>) {
  if (items.length === 0) {
    return (
      <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
        None configured.
      </p>
    )
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {items.map((item) => (
        <span
          key={item}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '3px 6px 3px 10px', borderRadius: 6,
            background: 'var(--surface-2)', border: '1px solid var(--border)',
            fontSize: '0.75rem', color: 'var(--text)', fontFamily: 'monospace',
          }}
        >
          {item}
          <button
            type="button"
            onClick={() => onRemove(item)}
            aria-label={`Remove ${item}`}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-muted)', padding: 2,
            }}
          >
            <X size={11} />
          </button>
        </span>
      ))}
    </div>
  )
}

function Toggle({
  label, value, onChange,
}: Readonly<{ label: string; value: boolean; onChange: (v: boolean) => void }>) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        background: 'none', border: 'none', cursor: 'pointer',
        padding: 0, textAlign: 'left',
      }}
    >
      <span style={{
        width: 32, height: 18, borderRadius: 10,
        background: value ? 'var(--accent)' : 'var(--surface-2)',
        border: '1px solid ' + (value ? 'var(--accent)' : 'var(--border)'),
        position: 'relative', flexShrink: 0, transition: 'background 0.15s',
      }}>
        <span style={{
          width: 12, height: 12, borderRadius: '50%',
          background: '#fff', position: 'absolute',
          top: 2, left: value ? 17 : 2,
          transition: 'left 0.15s',
        }} />
      </span>
      <span style={{ fontSize: '0.8125rem', color: 'var(--text)' }}>{label}</span>
    </button>
  )
}
