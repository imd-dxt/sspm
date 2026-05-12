import { useState, useMemo } from 'react'
import { AppWindow, Search, AlertTriangle } from 'lucide-react'
import { useThirdPartyApps, type ThirdPartyApp } from '../api/thirdPartyApps'
import SeverityBadge from '../components/findings/SeverityBadge'
import PlatformLogo from '../components/shared/PlatformLogo'
import { platformLabel, formatRelative } from '../lib/utils'

function resourceTypeLabel(rt: string): string {
  const map: Record<string, string> = {
    oauth_app: 'OAuth App',
    github_app: 'GitHub App',
    service_principal: 'Service Principal',
    app_registration: 'App Registration',
    connected_app: 'Connected App',
    marketplace_app: 'Marketplace App',
    integration: 'Integration',
  }
  return map[rt] ?? rt.replaceAll('_', ' ')
}

function AppRow({ app }: Readonly<{ app: ThirdPartyApp }>) {
  return (
    <div className="data-row" style={{ gridTemplateColumns: '28px 1fr 130px 120px 80px 80px 90px' }}>
      <PlatformLogo platform={app.platform} size={28} />

      <div style={{ minWidth: 0 }}>
        <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {app.name}
        </p>
        {app.connector_name && (
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 2 }}>
            {app.connector_name}
          </p>
        )}
      </div>

      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{platformLabel(app.platform)}</span>

      <span
        style={{
          display: 'inline-flex', alignItems: 'center', borderRadius: 20,
          padding: '2px 9px', fontSize: '0.6875rem', fontWeight: 500,
          background: 'color-mix(in oklch, var(--text-muted) 10%, transparent)',
          color: 'var(--text-muted)',
          whiteSpace: 'nowrap',
        }}
      >
        {resourceTypeLabel(app.resource_type)}
      </span>

      <span style={{ fontSize: '0.75rem', fontVariantNumeric: 'tabular-nums', color: app.open_findings > 0 ? 'var(--sev-high)' : 'var(--text-muted)' }}>
        {app.open_findings > 0 ? `${app.open_findings} open` : '—'}
      </span>

      <span>
        {app.highest_severity ? <SeverityBadge severity={app.highest_severity} /> : <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>—</span>}
      </span>

      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
        {formatRelative(app.last_seen)}
      </span>
    </div>
  )
}

export default function ThirdPartyApps() {
  const [search, setSearch] = useState('')
  const [platformFilter, setPlatformFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const { data, isLoading, isError, refetch } = useThirdPartyApps()

  const uniquePlatforms = useMemo(() => {
    const ps = new Set(data?.apps.map((a) => a.platform) ?? [])
    return Array.from(ps).sort((a, b) => a.localeCompare(b))
  }, [data])

  const uniqueTypes = useMemo(() => {
    const ts = new Set(data?.apps.map((a) => a.resource_type) ?? [])
    return Array.from(ts).sort((a, b) => a.localeCompare(b))
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    return data.apps.filter((a) => {
      if (platformFilter && a.platform !== platformFilter) return false
      if (typeFilter && a.resource_type !== typeFilter) return false
      if (search.trim()) {
        const q = search.toLowerCase()
        return (
          a.name.toLowerCase().includes(q) ||
          (a.connector_name ?? '').toLowerCase().includes(q) ||
          platformLabel(a.platform).toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [data, search, platformFilter, typeFilter])

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Third-Party Apps</h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>
            OAuth apps, service principals, and integrations detected across connected platforms
          </p>
        </div>
      </div>

      {/* Stat strip */}
      {!isLoading && data && (
        <div className="stat-strip">
          <div className="stat-cell">
            <span className="stat-value">{data.total_apps}</span>
            <span className="stat-label">Apps detected</span>
          </div>
          <div className="stat-cell">
            <span className="stat-value" style={{ color: data.risky_apps > 0 ? 'var(--sev-high)' : 'var(--ok)' }}>
              {data.risky_apps}
            </span>
            <span className="stat-label">Risky (crit/high)</span>
          </div>
          <div className="stat-cell" style={{ borderRight: 'none' }}>
            <span className="stat-value">{data.connectors_scanned}</span>
            <span className="stat-label">Connectors scanned</span>
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="filter-bar">
        <div style={{ position: 'relative', flex: 1, minWidth: 180, maxWidth: 280 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input
            type="text"
            className="input"
            style={{ paddingLeft: 30, paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem' }}
            placeholder="Search apps…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {uniquePlatforms.length > 0 && (
          <select
            className="select"
            style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', width: 'auto', minWidth: 130 }}
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
          >
            <option value="">All platforms</option>
            {uniquePlatforms.map((p) => (
              <option key={p} value={p}>{platformLabel(p)}</option>
            ))}
          </select>
        )}
        {uniqueTypes.length > 0 && (
          <select
            className="select"
            style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', width: 'auto', minWidth: 150 }}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All types</option>
            {uniqueTypes.map((t) => (
              <option key={t} value={t}>{resourceTypeLabel(t)}</option>
            ))}
          </select>
        )}
        <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {isLoading ? '…' : `${filtered.length} apps`}
        </span>
      </div>

      {/* Error */}
      {isError && (
        <div style={{
          borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12,
          background: 'color-mix(in oklch, var(--sev-critical) 10%, transparent)',
          border: '1px solid color-mix(in oklch, var(--sev-critical) 25%, transparent)',
          marginBottom: 14,
        }}>
          <AlertTriangle size={15} style={{ color: 'var(--sev-critical)', flexShrink: 0 }} />
          <p style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', flex: 1 }}>
            Failed to load third-party apps.
          </p>
          <button onClick={() => refetch()} style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
            Retry
          </button>
        </div>
      )}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="data-table">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="data-row" style={{ gridTemplateColumns: '28px 1fr 130px 120px 80px 80px 90px' }}>
              <div className="skeleton" style={{ width: 28, height: 28, borderRadius: 6 }} />
              <div>
                <div className="skeleton" style={{ height: 14, width: '55%', marginBottom: 5 }} />
                <div className="skeleton" style={{ height: 11, width: '35%' }} />
              </div>
              <div className="skeleton" style={{ height: 14, width: 80 }} />
              <div className="skeleton" style={{ height: 20, borderRadius: 20, width: 100 }} />
              <div className="skeleton" style={{ height: 14, width: 50 }} />
              <div className="skeleton" style={{ height: 20, borderRadius: 6, width: 60 }} />
              <div className="skeleton" style={{ height: 14, width: 60 }} />
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {!isLoading && !isError && (
        filtered.length === 0 ? (
          <div className="empty-state">
            <AppWindow size={28} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
            <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
              {data?.total_apps === 0 ? 'No third-party apps detected' : 'No apps match your filters'}
            </p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', maxWidth: 360 }}>
              {data?.total_apps === 0
                ? 'Third-party apps are detected automatically during connector syncs. Sync your connectors to discover OAuth apps, GitHub Apps, service principals, and other integrations.'
                : 'Try adjusting your search or filters.'}
            </p>
          </div>
        ) : (
          <div className="data-table">
            <div className="table-head" style={{ display: 'grid', gridTemplateColumns: '28px 1fr 130px 120px 80px 80px 90px' }}>
              <span />
              <span>App / Connector</span>
              <span>Platform</span>
              <span>Type</span>
              <span>Findings</span>
              <span>Risk</span>
              <span>Last seen</span>
            </div>
            {filtered.map((app) => <AppRow key={app.id} app={app} />)}
          </div>
        )
      )}
    </div>
  )
}
