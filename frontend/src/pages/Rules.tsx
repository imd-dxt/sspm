import { useState, useMemo } from 'react'
import { Search, ChevronDown, ChevronRight, BookOpen } from 'lucide-react'
import { useRules } from '../api/rules'
import SeverityBadge from '../components/findings/SeverityBadge'
import { platformLabel } from '../lib/utils'
import type { Rule } from '../api/types'

function RuleRow({ rule }: Readonly<{ rule: Rule }>) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div>
      <button
        onClick={() => setExpanded((e) => !e)}
        style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
      >
        <div className="data-row" style={{ gridTemplateColumns: '90px 1fr 130px 120px 56px 20px' }}>
          <SeverityBadge severity={rule.severity} />
          <div style={{ minWidth: 0 }}>
            <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {rule.name}
            </p>
            <p style={{ fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: 2 }}>
              {rule.id}
            </p>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{platformLabel(rule.platform)}</span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>{rule.category}</span>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              borderRadius: 20,
              padding: '2px 9px',
              fontSize: '0.6875rem',
              fontWeight: 600,
              color: rule.is_active ? 'var(--ok)' : 'var(--text-muted)',
              background: rule.is_active
                ? 'color-mix(in oklch, var(--ok) 12%, transparent)'
                : 'color-mix(in oklch, var(--text-muted) 12%, transparent)',
            }}
          >
            {rule.is_active ? 'Active' : 'Off'}
          </span>
          {expanded ? <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} /> : <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />}
        </div>
      </button>

      {expanded && (
        <div style={{ padding: '16px 20px', background: 'var(--surface-2)', borderBottom: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <p className="label">Description</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text)' }}>{rule.description}</p>
          </div>
          <div>
            <p className="label">Remediation</p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text)' }}>{rule.remediation}</p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            <div>
              <p className="label">Query type</p>
              <p style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: 'var(--text)' }}>{rule.query_type}</p>
            </div>
            {rule.cis_control && (
              <div>
                <p className="label">CIS Control</p>
                <p style={{ fontSize: '0.875rem', color: 'var(--text)' }}>{rule.cis_control}</p>
              </div>
            )}
            {rule.profile && (
              <div>
                <p className="label">Profile</p>
                <p style={{ fontSize: '0.875rem', color: 'var(--text)' }}>{rule.profile}</p>
              </div>
            )}
          </div>
          {rule.detection_query && (
            <div>
              <p className="label">Detection Query</p>
              <pre className="code-block">{rule.detection_query}</pre>
            </div>
          )}
          {rule.referentials?.length > 0 && (
            <div>
              <p className="label">Standards</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {rule.referentials.map((ref) => (
                  <span key={ref} style={{
                    borderRadius: 6, background: 'color-mix(in oklch, var(--accent) 10%, transparent)',
                    border: '1px solid color-mix(in oklch, var(--accent) 30%, transparent)',
                    padding: '2px 8px', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--accent)',
                  }}>{ref}</span>
                ))}
              </div>
            </div>
          )}
          {(rule.compliance_mapping ?? []).length > 0 && (
            <div>
              <p className="label">Compliance</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {(rule.compliance_mapping ?? []).map((c) => (
                  <span key={c} style={{
                    borderRadius: 6, background: 'var(--surface)', border: '1px solid var(--border)',
                    padding: '2px 8px', fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)',
                  }}>{c}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const REFERENTIALS = ['CIS', 'ISO27001', 'NIST', 'SOC2']

export default function Rules() {
  const [search, setSearch] = useState('')
  const [platformFilter, setPlatformFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [referentialFilter, setReferentialFilter] = useState('')

  const { data, isLoading, isError, refetch } = useRules()

  const platforms = useMemo(() => {
    const ps = new Set(data?.map((r) => r.platform) ?? [])
    return Array.from(ps).sort((a, b) => a.localeCompare(b))
  }, [data])

  const filtered = useMemo(() => {
    if (!data) return []
    return data.filter((r) => {
      if (platformFilter && r.platform !== platformFilter) return false
      if (severityFilter && r.severity !== severityFilter) return false
      if (referentialFilter && !(r.referentials ?? []).includes(referentialFilter)) return false
      if (search.trim()) {
        const q = search.toLowerCase()
        return (
          r.name.toLowerCase().includes(q) ||
          r.id.toLowerCase().includes(q) ||
          r.description.toLowerCase().includes(q) ||
          r.category.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [data, search, platformFilter, severityFilter, referentialFilter])

  const activeCount = data?.filter((r) => r.is_active).length ?? 0
  const totalCount = data?.length ?? 0

  return (
    <div>
      {/* Stats + filter row */}
      <div className="filter-bar">
        {!isLoading && data && (
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', flexShrink: 0 }}>
            <strong style={{ color: 'var(--text)' }}>{activeCount}</strong> active ·{' '}
            <strong style={{ color: 'var(--text)' }}>{totalCount}</strong> total
          </span>
        )}
        <div style={{ position: 'relative', flex: 1, minWidth: 180, maxWidth: 280 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input
            type="text"
            className="input"
            style={{ paddingLeft: 30, paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem' }}
            placeholder="Search rules…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="select"
          style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', width: 'auto', minWidth: 130 }}
          value={platformFilter}
          onChange={(e) => setPlatformFilter(e.target.value)}
        >
          <option value="">All platforms</option>
          {platforms.map((p) => (
            <option key={p} value={p}>{platformLabel(p)}</option>
          ))}
        </select>
        <select
          className="select"
          style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', width: 'auto', minWidth: 130 }}
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
        >
          <option value="">All severities</option>
          {['critical', 'high', 'medium', 'low', 'info'].map((s) => (
            <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
          ))}
        </select>
        <select
          className="select"
          style={{ paddingTop: 6, paddingBottom: 6, fontSize: '0.8125rem', width: 'auto', minWidth: 130 }}
          value={referentialFilter}
          onChange={(e) => setReferentialFilter(e.target.value)}
        >
          <option value="">All standards</option>
          {REFERENTIALS.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>
          {isLoading ? '…' : `${filtered.length} rules`}
        </span>
      </div>

      {isError && (
        <div style={{
          borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12,
          background: 'color-mix(in oklch, var(--sev-critical) 10%, transparent)',
          border: '1px solid color-mix(in oklch, var(--sev-critical) 25%, transparent)',
          marginBottom: 14,
        }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', flex: 1 }}>Failed to load rules.</p>
          <button onClick={() => refetch()} style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>Retry</button>
        </div>
      )}

      {isLoading && (
        <div className="data-table">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="data-row" style={{ gridTemplateColumns: '90px 1fr 130px 120px 56px 20px' }}>
              <div className="skeleton" style={{ height: 20, borderRadius: 6 }} />
              <div className="skeleton" style={{ height: 14 }} />
              <div className="skeleton" style={{ height: 14, width: 80 }} />
              <div className="skeleton" style={{ height: 14, width: 80 }} />
              <div className="skeleton" style={{ height: 20, borderRadius: 20, width: 50 }} />
              <div />
            </div>
          ))}
        </div>
      )}

      {!isLoading && !isError && (
        filtered.length === 0 ? (
          <div className="empty-state">
            <BookOpen size={28} style={{ color: 'var(--text-muted)', marginBottom: 12 }} />
            <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
              {data?.length === 0 ? 'No rules found' : 'No rules match your filters'}
            </p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              {data?.length === 0 ? 'Rules are loaded from your backend configuration.' : 'Try adjusting your search or filters.'}
            </p>
          </div>
        ) : (
          <div className="data-table">
            <div className="table-head" style={{ display: 'grid', gridTemplateColumns: '90px 1fr 130px 120px 56px 20px' }}>
              <span>Severity</span>
              <span>Rule</span>
              <span>Platform</span>
              <span>Category</span>
              <span>Status</span>
              <span />
            </div>
            {filtered.map((rule) => <RuleRow key={rule.id} rule={rule} />)}
          </div>
        )
      )}
    </div>
  )
}
