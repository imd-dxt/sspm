import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Users, Grid3x3, Shield, Map, Search, Filter, ShieldCheck } from 'lucide-react'
import PlatformLogo from '../components/shared/PlatformLogo'
import ForceGraph from '../components/identities/ForceGraph'
import {
  useIdentitySummary,
  useIdentityUsers,
  useIdentityResources,
  useFindingsByResource,
  useIdentityGraph,
} from '../api/identities'
import type { IdentityResourceRow } from '../api/types'
import { platformLabel } from '../lib/utils'

// ── Tabs ───────────────────────────────────────────────────────────────────────

type Tab = 'users' | 'groups' | 'roles' | 'map'

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'users',  label: 'Users',               icon: <Users size={14} /> },
  { id: 'groups', label: 'Groups / Teams',       icon: <Grid3x3 size={14} /> },
  { id: 'roles',  label: 'Roles & Permissions',  icon: <Shield size={14} /> },
  { id: 'map',    label: 'Access Map',           icon: <Map size={14} /> },
]

function TabBar({
  active, onChange, counts,
}: Readonly<{ active: Tab; onChange: (t: Tab) => void; counts: Partial<Record<Tab, number>> }>) {
  return (
    <div style={{
      display: 'flex', gap: 2,
      background: 'var(--surface-2)', border: '1px solid var(--border)',
      borderRadius: 10, padding: 4, flexWrap: 'wrap',
    }}>
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          style={{
            display: 'flex', alignItems: 'center', gap: 7,
            padding: '7px 16px', borderRadius: 7, border: 'none',
            fontSize: '0.8125rem', fontWeight: 500, cursor: 'pointer',
            transition: 'all 0.12s',
            background: active === t.id ? 'var(--surface)' : 'transparent',
            color: active === t.id ? 'var(--text)' : 'var(--text-muted)',
            boxShadow: active === t.id ? '0 1px 4px rgba(0,0,0,0.10)' : 'none',
          }}
        >
          {t.icon}
          {t.label}
          {counts[t.id] != null && (
            <span style={{
              minWidth: 20, height: 18, borderRadius: 9, padding: '0 5px',
              background: active === t.id ? 'var(--accent)' : 'var(--border)',
              color: active === t.id ? '#fff' : 'var(--text-muted)',
              fontSize: '0.625rem', fontWeight: 700,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {counts[t.id]}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

// ── KPI Strip ──────────────────────────────────────────────────────────────────

function KpiStrip({ total, admins, atRisk, resources }: Readonly<{
  total: number; admins: number; atRisk: number; resources: number
}>) {
  const kpis = [
    { label: 'Total Users',   value: total,     color: 'var(--accent)' },
    { label: 'Admins',        value: admins,    color: 'var(--sev-critical)' },
    { label: 'Users at Risk', value: atRisk,    color: 'var(--sev-high)' },
    { label: 'Resources',     value: resources, color: 'var(--sev-medium)' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
      {kpis.map((k) => (
        <div key={k.label} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px' }}>
          <p style={{ fontSize: '1.75rem', fontWeight: 700, color: k.color, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{k.value}</p>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500, marginTop: 4 }}>{k.label}</p>
        </div>
      ))}
    </div>
  )
}

// ── Users tab ──────────────────────────────────────────────────────────────────

type UserFilter = 'all' | 'admins' | 'at_risk' | 'external' | 'inactive'

const USER_FILTER_BTNS: { id: UserFilter; label: string }[] = [
  { id: 'all',      label: 'All' },
  { id: 'admins',   label: 'Admins' },
  { id: 'at_risk',  label: 'At risk' },
  { id: 'external', label: 'External' },
  { id: 'inactive', label: 'Inactive' },
]

function UsersTab({ platform }: Readonly<{ platform: string }>) {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<UserFilter>('all')

  const { data: rawUsers, isLoading } = useIdentityUsers(platform, undefined, 500)
  const users = rawUsers ?? []

  const filtered = useMemo(() => {
    let list = users
    if (filter === 'admins')   list = list.filter((u) => u.is_admin)
    if (filter === 'at_risk')  list = list.filter((u) => u.finding_count > 0)
    if (filter === 'external') list = list.filter((u) => u.is_external)
    if (filter === 'inactive') list = list.filter((u) => !u.is_active)
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (u) => (u.display_name || u.username).toLowerCase().includes(q) || (u.email ?? '').toLowerCase().includes(q),
      )
    }
    return list
  }, [users, filter, search])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', padding: '10px 14px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}>
        <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 180 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or email…"
            style={{ width: '100%', padding: '6px 10px 6px 30px', fontSize: '0.8125rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
          />
        </div>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
          <Filter size={12} style={{ color: 'var(--text-muted)', marginRight: 2 }} />
          {USER_FILTER_BTNS.map((fb) => (
            <FilterPill key={fb.id} label={fb.label} active={filter === fb.id} onClick={() => setFilter(fb.id)} />
          ))}
        </div>
        <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {isLoading ? '…' : `${filtered.length} users`}
        </span>
      </div>

      {/* Table */}
      {isLoading ? (
        <TableSkeleton />
      ) : filtered.length === 0 ? (
        <EmptyState message="No users match your filter." />
      ) : (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px 80px 80px', padding: '10px 16px', borderBottom: '1px solid var(--border)', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            <span>User</span>
            <span style={{ textAlign: 'center' }}>Role</span>
            <span style={{ textAlign: 'right' }}>Findings</span>
            <span style={{ textAlign: 'right' }}>Resources</span>
          </div>
          {filtered.map((u) => (
            <UserRow key={u.id} user={u} />
          ))}
        </div>
      )}
    </div>
  )
}

function UserRow({ user }: Readonly<{ user: IdentityUser }>) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px 80px 80px', padding: '11px 16px', borderBottom: '1px solid var(--border)', alignItems: 'center', fontSize: '0.8125rem' }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <p style={{ fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user.display_name || user.username}
          </p>
          {!user.is_active && (
            <span style={{ fontSize: '0.625rem', padding: '1px 6px', borderRadius: 10, background: 'var(--surface-2)', color: 'var(--text-muted)', flexShrink: 0 }}>Inactive</span>
          )}
          {user.is_external && (
            <span style={{ fontSize: '0.625rem', padding: '1px 6px', borderRadius: 10, background: 'color-mix(in oklch, #f59e0b 12%, transparent)', color: '#f59e0b', flexShrink: 0 }}>External</span>
          )}
        </div>
        {user.email && (
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 2 }}>{user.email}</p>
        )}
      </div>
      <div style={{ textAlign: 'center' }}>
        {user.is_admin ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 20, fontSize: '0.6875rem', fontWeight: 600, background: 'color-mix(in oklch, var(--sev-critical) 14%, transparent)', color: 'var(--sev-critical)' }}>
            <ShieldCheck size={10} />Admin
          </span>
        ) : (
          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>—</span>
        )}
      </div>
      <p style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: user.finding_count > 0 ? 'var(--sev-high)' : 'var(--text-muted)', fontWeight: user.finding_count > 0 ? 600 : 400 }}>
        {user.finding_count > 0 ? user.finding_count : '—'}
      </p>
      <p style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: 'var(--text-muted)' }}>
        {user.resource_count > 0 ? user.resource_count : '—'}
      </p>
    </div>
  )
}

// ── Groups / Teams tab ─────────────────────────────────────────────────────────

const GROUP_TYPES = new Set(['group', 'team', 'Group', 'Team', 'security_group', 'M365', 'Dynamic'])

function GroupsTab({ platform }: Readonly<{ platform: string }>) {
  const [search, setSearch] = useState('')
  const { data: rawResources, isLoading } = useIdentityResources(platform, undefined, 500)

  const resources = rawResources ?? []
  const groups = useMemo(() => {
    const base = resources.filter((r) => GROUP_TYPES.has(r.resource_type ?? ''))
    if (!search.trim()) return base
    const q = search.toLowerCase()
    return base.filter((r) => r.name.toLowerCase().includes(q))
  }, [resources, search])

  return (
    <ResourceList
      label="Groups / Teams"
      emptyMsg="No groups or teams found for this platform."
      rows={groups}
      isLoading={isLoading}
      search={search}
      onSearch={setSearch}
    />
  )
}

// ── Roles & Permissions tab ────────────────────────────────────────────────────

const ROLE_TYPES = new Set(['role', 'Role', 'directory_role', 'DirectoryRole'])

function RolesTab({ platform }: Readonly<{ platform: string }>) {
  const [search, setSearch] = useState('')
  const { data: rawResources, isLoading } = useIdentityResources(platform, undefined, 500)

  const resources = rawResources ?? []
  const roles = useMemo(() => {
    const base = resources.filter((r) => ROLE_TYPES.has(r.resource_type ?? ''))
    if (!search.trim()) return base
    const q = search.toLowerCase()
    return base.filter((r) => r.name.toLowerCase().includes(q))
  }, [resources, search])

  return (
    <ResourceList
      label="Roles & Permissions"
      emptyMsg="No roles found for this platform."
      rows={roles}
      isLoading={isLoading}
      search={search}
      onSearch={setSearch}
    />
  )
}

// ── Shared ResourceList ────────────────────────────────────────────────────────

function ResourceList({ label, emptyMsg, rows, isLoading, search, onSearch }: Readonly<{
  label: string
  emptyMsg: string
  rows: IdentityResourceRow[]
  isLoading: boolean
  search: string
  onSearch: (v: string) => void
}>) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '10px 14px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}>
        <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 180 }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input
            type="text"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder={`Search ${label.toLowerCase()}…`}
            style={{ width: '100%', padding: '6px 10px 6px 30px', fontSize: '0.8125rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
          />
        </div>
        <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
          {isLoading ? '…' : `${rows.length} ${label.toLowerCase()}`}
        </span>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : rows.length === 0 ? (
        <EmptyState message={search ? `No ${label.toLowerCase()} match your search.` : emptyMsg} />
      ) : (
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 80px 80px 80px', padding: '10px 16px', borderBottom: '1px solid var(--border)', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            <span>Name</span>
            <span style={{ textAlign: 'right' }}>Findings</span>
            <span style={{ textAlign: 'right' }}>Crit</span>
            <span style={{ textAlign: 'right' }}>High</span>
            <span style={{ textAlign: 'right' }}>Med</span>
            <span style={{ textAlign: 'right' }}>Low</span>
          </div>
          {rows.map((row) => (
            <div
              key={row.platform_id}
              style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 80px 80px 80px', padding: '11px 16px', borderBottom: '1px solid var(--border)', alignItems: 'center', fontSize: '0.8125rem' }}
            >
              <p style={{ color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }}>{row.name}</p>
              <SevNum value={row.finding_count} color="var(--sev-high)" />
              <SevNum value={row.critical} color="var(--sev-critical)" />
              <SevNum value={row.high} color="var(--sev-high)" />
              <SevNum value={row.medium} color="var(--sev-medium)" />
              <SevNum value={row.low} color="var(--sev-low)" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SevNum({ value, color }: Readonly<{ value: number; color: string }>) {
  return (
    <p style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: value > 0 ? color : 'var(--text-muted)', fontWeight: value > 0 ? 600 : 400 }}>
      {value > 0 ? value : '—'}
    </p>
  )
}

// ── Access Map tab ─────────────────────────────────────────────────────────────

function AccessMapTab({ platform, users }: Readonly<{ platform: string; users: IdentityUser[] }>) {
  const { data, isLoading } = useIdentityGraph(platform)
  const [focusId, setFocusId] = useState('')
  const [resourceSearch, setResourceSearch] = useState('')

  const resources = useMemo(
    () => data?.nodes.filter((n) => n.type === 'resource').sort((a, b) => a.label.localeCompare(b.label)) ?? [],
    [data],
  )

  const visibleResources = useMemo(() => {
    if (!resourceSearch.trim()) return resources
    const q = resourceSearch.toLowerCase()
    return resources.filter((r) => r.label.toLowerCase().includes(q) || r.platform_id.toLowerCase().includes(q))
  }, [resources, resourceSearch])

  const { filteredNodes, filteredEdges } = useMemo(() => {
    if (!data) return { filteredNodes: [], filteredEdges: [] }
    if (!focusId) return { filteredNodes: data.nodes, filteredEdges: data.edges }
    const relEdges = data.edges.filter((e) => e.target === focusId)
    const userIds  = new Set(relEdges.map((e) => e.source))
    const nodeIds  = new Set([focusId, ...userIds])
    return {
      filteredNodes: data.nodes.filter((n) => nodeIds.has(n.id)),
      filteredEdges: relEdges,
    }
  }, [data, focusId])

  if (isLoading) {
    return <div style={{ height: 120, background: 'var(--surface-2)', borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>Loading access map…</div>
  }

  if (!data || data.nodes.length === 0) {
    return <EmptyState message="No permission data available to build the access map." />
  }

  const selected = resources.find((r) => r.id === focusId)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 16px' }}>
        <p style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
          Filter by Resource
        </p>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1 1 200px', minWidth: 180 }}>
            <Search size={12} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
            <input
              type="text"
              value={resourceSearch}
              onChange={(e) => setResourceSearch(e.target.value)}
              placeholder="Search resources…"
              style={{ width: '100%', padding: '7px 10px 7px 28px', fontSize: '0.8125rem', background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)' }}
            />
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: '3 1 300px' }}>
            <button
              onClick={() => setFocusId('')}
              style={{
                padding: '5px 14px', borderRadius: 20, fontSize: '0.75rem', fontWeight: 500, cursor: 'pointer',
                border: `1.5px solid ${focusId === '' ? 'var(--accent)' : 'var(--border)'}`,
                background: focusId === '' ? 'color-mix(in oklch, var(--accent) 10%, var(--surface))' : 'var(--surface)',
                color: focusId === '' ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              All ({resources.length})
            </button>
            {visibleResources.slice(0, 30).map((r) => (
              <button
                key={r.id}
                onClick={() => setFocusId(r.id === focusId ? '' : r.id)}
                style={{
                  padding: '5px 14px', borderRadius: 20, fontSize: '0.75rem', fontWeight: 500, cursor: 'pointer',
                  border: `1.5px solid ${focusId === r.id ? '#0ea5e9' : 'var(--border)'}`,
                  background: focusId === r.id ? 'color-mix(in oklch, #0ea5e9 10%, var(--surface))' : 'var(--surface)',
                  color: focusId === r.id ? '#0ea5e9' : 'var(--text-muted)',
                  maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}
                title={r.label}
              >
                {r.label.length > 22 ? `${r.label.slice(0, 20)}…` : r.label}
              </button>
            ))}
            {visibleResources.length > 30 && (
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', alignSelf: 'center', padding: '5px 8px' }}>
                +{visibleResources.length - 30} more — narrow search
              </span>
            )}
          </div>
        </div>
        {selected && (
          <div style={{ marginTop: 10, padding: '8px 12px', background: 'color-mix(in oklch, #0ea5e9 6%, var(--surface-2))', borderRadius: 8, border: '1px solid color-mix(in oklch, #0ea5e9 20%, transparent)', fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ color: '#0ea5e9', fontWeight: 600 }}>↓</span>
            Showing {filteredNodes.filter((n) => n.type === 'user').length} user{filteredNodes.filter((n) => n.type === 'user').length === 1 ? '' : 's'} with access to{' '}
            <strong style={{ color: 'var(--text)' }}>{selected.label}</strong>
          </div>
        )}
      </div>
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        Force-directed graph · Drag nodes, scroll to zoom · Hover for details
      </p>
      {filteredNodes.length === 0
        ? <EmptyState message="No connections found for this resource." />
        : <ForceGraph nodes={filteredNodes} edges={filteredEdges} users={users} />
      }
    </div>
  )
}

// ── Shared helpers ─────────────────────────────────────────────────────────────

function FilterPill({ label, active, onClick }: Readonly<{ label: string; active: boolean; onClick: () => void }>) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '4px 12px', borderRadius: 20, fontSize: '0.75rem', fontWeight: 500, cursor: 'pointer',
        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
        background: active ? 'color-mix(in oklch, var(--accent) 10%, var(--surface))' : 'var(--surface)',
        color: active ? 'var(--accent)' : 'var(--text-muted)',
        transition: 'all 0.12s',
      }}
    >
      {label}
    </button>
  )
}

const TABLE_SKELETON_ROWS = ['sk-a', 'sk-b', 'sk-c', 'sk-d', 'sk-e', 'sk-f']

function TableSkeleton() {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, overflow: 'hidden' }}>
      {TABLE_SKELETON_ROWS.map((id, i) => (
        <div key={id} style={{ height: 48, borderBottom: '1px solid var(--border)', background: 'var(--surface-2)', animation: 'pulse 1.5s ease-in-out infinite', animationDelay: `${i * 80}ms` }} />
      ))}
    </div>
  )
}

function EmptyState({ message }: Readonly<{ message: string }>) {
  return (
    <div style={{ padding: '32px 24px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
      {message}
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function IdentityDetail() {
  const { platform = '' } = useParams<{ platform: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<Tab>('users')

  const { data: summary, isLoading: summaryLoading } = useIdentitySummary(platform)
  const { data: usersData } = useIdentityUsers(platform, undefined, 500)
  const { data: resourcesData } = useIdentityResources(platform, undefined, 500)
  const { data: findingsByResource } = useFindingsByResource(platform, undefined, 500)

  const groupCount = useMemo(
    () => (resourcesData ?? []).filter((r) => GROUP_TYPES.has(r.resource_type ?? '')).length,
    [resourcesData],
  )
  const roleCount = useMemo(
    () => (resourcesData ?? []).filter((r) => ROLE_TYPES.has(r.resource_type ?? '')).length,
    [resourcesData],
  )

  const tabCounts: Partial<Record<Tab, number>> = {
    users:  usersData?.length,
    groups: groupCount || undefined,
    roles:  roleCount || undefined,
  }

  const kpi = summary ?? {
    total_users: 0,
    total_admins: 0,
    users_at_risk: 0,
    total_resources: findingsByResource?.length ?? 0,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Breadcrumb + header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <button
          onClick={() => navigate('/identities')}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '7px 14px', borderRadius: 8, fontSize: '0.8125rem', fontWeight: 500,
            border: '1.5px solid var(--border)', background: 'var(--surface)',
            color: 'var(--text-muted)', cursor: 'pointer',
          }}
        >
          <ArrowLeft size={14} />
          All platforms
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <PlatformLogo platform={platform} size={24} />
          <h2 style={{ fontSize: '1.0625rem', fontWeight: 700, color: 'var(--text)' }}>
            {platformLabel(platform)}
          </h2>
        </div>
      </div>

      {/* KPI strip */}
      {summaryLoading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {['k1', 'k2', 'k3', 'k4'].map((id) => (
            <div key={id} style={{ height: 80, borderRadius: 10, background: 'var(--surface-2)', animation: 'pulse 1.5s ease-in-out infinite' }} />
          ))}
        </div>
      ) : (
        <KpiStrip
          total={kpi.total_users}
          admins={kpi.total_admins}
          atRisk={kpi.users_at_risk}
          resources={kpi.total_resources}
        />
      )}

      {/* Tabs */}
      <TabBar active={activeTab} onChange={setActiveTab} counts={tabCounts} />

      {/* Tab content */}
      {activeTab === 'users'  && <UsersTab  platform={platform} />}
      {activeTab === 'groups' && <GroupsTab platform={platform} />}
      {activeTab === 'roles'  && <RolesTab  platform={platform} />}
      {activeTab === 'map'    && <AccessMapTab platform={platform} users={usersData ?? []} />}
    </div>
  )
}
