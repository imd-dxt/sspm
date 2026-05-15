import { useState } from 'react'
import { Plus, AlertCircle } from 'lucide-react'
import { useConnectors } from '../api/connectors'
import AddConnectorModal from '../components/connectors/AddConnectorModal'
import ConnectorPostureCard from '../components/connectors/ConnectorPostureCard'

function pctColor(p: number): string {
  if (p >= 80) return 'var(--ok)'
  if (p >= 50) return 'var(--sev-medium)'
  return 'var(--sev-high)'
}

const CARD_SKELETONS = ['sk-1', 'sk-2', 'sk-3']

export default function Connectors() {
  const [modalOpen, setModalOpen] = useState(false)
  const { data: connectors, isLoading, isError, refetch } = useConnectors()

  const total     = connectors?.length ?? 0
  const active    = connectors?.filter((c) => c.connection_ok === true).length ?? 0
  const failed    = connectors?.filter((c) => c.connection_ok === false).length ?? 0
  const notSynced = connectors?.filter((c) => c.connection_ok === null).length ?? 0
  const pct       = total > 0 ? Math.round((active / total) * 100) : 0

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>Global View</h2>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>
            All connected SaaS platforms and their security posture
          </p>
        </div>
        <button onClick={() => setModalOpen(true)} className="btn-primary">
          <Plus size={15} />
          Add Connector
        </button>
      </div>

      {!isLoading && (
        <div className="stat-strip">
          <div className="stat-cell">
            <span className="stat-value">{total}</span>
            <span className="stat-label">Total</span>
          </div>
          <div className="stat-cell">
            <span className="stat-value" style={{ color: 'var(--ok)' }}>{active}</span>
            <span className="stat-label">Connected</span>
          </div>
          <div className="stat-cell">
            <span className="stat-value" style={{ color: failed > 0 ? 'var(--sev-high)' : 'var(--text-muted)' }}>{failed}</span>
            <span className="stat-label">Failed</span>
          </div>
          <div className="stat-cell">
            <span className="stat-value" style={{ color: 'var(--text-muted)' }}>{notSynced}</span>
            <span className="stat-label">Not Synced</span>
          </div>
          <div className="stat-cell" style={{ borderRight: 'none' }}>
            <span className="stat-value" style={{ color: pctColor(pct) }}>{pct}%</span>
            <span className="stat-label">Coverage</span>
          </div>
        </div>
      )}

      {isError && (
        <div style={{
          borderRadius: 10, padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12,
          background: 'color-mix(in oklch, var(--sev-critical) 10%, transparent)',
          border: '1px solid color-mix(in oklch, var(--sev-critical) 25%, transparent)',
          marginBottom: 16,
        }}>
          <AlertCircle size={15} style={{ color: 'var(--sev-critical)' }} />
          <p style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', flex: 1 }}>Failed to load connectors.</p>
          <button
            onClick={() => refetch()}
            style={{ fontSize: '0.875rem', color: 'var(--sev-critical)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
          >
            Retry
          </button>
        </div>
      )}

      {isLoading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 300px))', gap: 16 }}>
          {CARD_SKELETONS.map((id, i) => (
            <div
              key={id}
              style={{ height: 320, borderRadius: 16, background: 'var(--surface-2)', animation: 'pulse 1.5s ease-in-out infinite', animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      )}

      {!isLoading && !isError && total === 0 && (
        <div className="empty-state">
          <div style={{ width: 48, height: 48, borderRadius: 12, background: 'var(--surface-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
            <Plus size={22} style={{ color: 'var(--text-muted)' }} />
          </div>
          <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>No connectors yet</p>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 20, maxWidth: 300 }}>
            Connect your first SaaS platform to start monitoring your security posture.
          </p>
          <button onClick={() => setModalOpen(true)} className="btn-primary">
            <Plus size={15} />
            Add your first connector
          </button>
        </div>
      )}

      {!isLoading && !isError && total > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 300px))', gap: 16 }}>
          {connectors!.map((c) => (
            <ConnectorPostureCard key={c.id} connector={c} />
          ))}
        </div>
      )}

      <AddConnectorModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  )
}
