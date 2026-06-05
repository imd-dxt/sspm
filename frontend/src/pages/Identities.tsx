import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import PlatformLogo from '../components/shared/PlatformLogo'
import { useIdentityPlatforms } from '../api/identities'
import { platformLabel, formatRelative } from '../lib/utils'
import IdentitySettingsPanel from '../components/identities/IdentitySettingsPanel'

const TABLE_SKELETONS = ['sk-a', 'sk-b', 'sk-c']

export default function Identities() {
  const navigate = useNavigate()
  const { data: platforms, isLoading } = useIdentityPlatforms()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <h1 style={{ fontSize: '1.375rem', fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>SaaS Identities</h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
          Unified view of users and access across your connected SaaS platforms.
        </p>
      </div>

      {/* Admin settings panel (collapsible) */}
      <IdentitySettingsPanel />

      {isLoading && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
          {TABLE_SKELETONS.map((id, i) => (
            <div
              key={id}
              style={{ height: 60, borderBottom: '1px solid var(--border)', background: 'var(--surface-2)', animation: 'pulse 1.5s ease-in-out infinite', animationDelay: `${i * 80}ms` }}
            />
          ))}
        </div>
      )}

      {!isLoading && (!platforms || platforms.length === 0) && (
        <div style={{ padding: '48px 24px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          No platforms synced yet. Connect a SaaS platform to get started.
        </div>
      )}

      {!isLoading && platforms && platforms.length > 0 && (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
          {/* Table header */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '2fr 100px 110px 140px 120px',
            padding: '10px 16px', borderBottom: '1px solid var(--border)',
            fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)',
            textTransform: 'uppercase', letterSpacing: '0.05em',
          }}>
            <span>SaaS App</span>
            <span style={{ textAlign: 'right' }}>Users</span>
            <span style={{ textAlign: 'right' }}>Resources</span>
            <span>Last Sync</span>
            <span>Status</span>
          </div>

          {platforms.map((p) => (
            <PlatformRow
              key={p.platform}
              platform={p.platform}
              connectorName={p.connector_name}
              userCount={p.user_count}
              resourceCount={p.resource_count}
              lastSyncAt={p.last_sync_at}
              connectionOk={p.connection_ok}
              onClick={() => navigate(`/identities/${p.platform}`)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function PlatformRow({
  platform, connectorName, userCount, resourceCount, lastSyncAt, connectionOk, onClick,
}: Readonly<{
  platform: string
  connectorName: string
  userCount: number
  resourceCount: number
  lastSyncAt: string | null
  connectionOk: boolean | null
  onClick: () => void
}>) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'grid',
        gridTemplateColumns: '2fr 100px 110px 140px 120px',
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
        alignItems: 'center', width: '100%', background: 'none', border: 'none',
        cursor: 'pointer', textAlign: 'left', transition: 'background 0.1s',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-2)' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
    >
      {/* App identity */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <PlatformLogo platform={platform} size={28} />
        <div>
          <p style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text)' }}>
            {connectorName || platformLabel(platform)}
          </p>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 1 }}>
            {platformLabel(platform)}
          </p>
        </div>
      </div>

      {/* Users */}
      <p style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 600, color: 'var(--text)', fontSize: '0.9375rem' }}>
        {userCount.toLocaleString()}
      </p>

      {/* Resources */}
      <p style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
        {resourceCount.toLocaleString()}
      </p>

      {/* Last sync */}
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        {formatRelative(lastSyncAt)}
      </p>

      {/* Status + chevron */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <StatusPill connectionOk={connectionOk} />
        <ChevronRight size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
      </div>
    </button>
  )
}

function StatusPill({ connectionOk }: Readonly<{ connectionOk: boolean | null }>) {
  if (connectionOk === true) {
    return (
      <span style={{ padding: '2px 8px', borderRadius: 20, fontSize: '0.6875rem', fontWeight: 600, background: 'color-mix(in oklch, var(--ok) 12%, transparent)', color: 'var(--ok)' }}>
        Connected
      </span>
    )
  }
  if (connectionOk === false) {
    return (
      <span style={{ padding: '2px 8px', borderRadius: 20, fontSize: '0.6875rem', fontWeight: 600, background: 'color-mix(in oklch, var(--sev-critical) 12%, transparent)', color: 'var(--sev-critical)' }}>
        Error
      </span>
    )
  }
  return (
    <span style={{ padding: '2px 8px', borderRadius: 20, fontSize: '0.6875rem', background: 'var(--surface-2)', color: 'var(--text-muted)' }}>
      Not synced
    </span>
  )
}
