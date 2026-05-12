import { useLocation } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import NotificationBell from './NotificationBell'

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/connectors': 'Connectors',
  '/findings': 'Findings',
  '/third-party-apps': 'Third-Party Apps',
  '/rules': 'Rules',
  '/identities': 'Identities',
  '/scan-runs': 'Scan Runs',
  '/settings': 'Settings',
}

export default function Topbar() {
  const location = useLocation()
  const qc = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)

  const title = PAGE_TITLES[location.pathname] ?? 'SSPM'

  async function handleRefresh() {
    setRefreshing(true)
    await qc.invalidateQueries()
    setTimeout(() => setRefreshing(false), 600)
  }

  return (
    <header className="topbar">
      <h1 style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)' }}>{title}</h1>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <NotificationBell />
        <button
          onClick={handleRefresh}
          className="btn-ghost"
          title="Refresh all data"
          aria-label="Refresh"
        >
          <RefreshCw
            size={14}
            style={{
              transition: 'transform 0.3s',
              animation: refreshing ? 'spin 0.6s linear infinite' : undefined,
            }}
          />
          <span style={{ display: 'none' }}>Refresh</span>
        </button>
      </div>
    </header>
  )
}
