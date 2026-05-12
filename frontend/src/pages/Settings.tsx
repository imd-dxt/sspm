import { useState } from 'react'
import { Save, Info, RefreshCw, Loader2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

function Section({ title, description, children }: Readonly<{ title: string; description: string; children: React.ReactNode }>) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <div style={{ marginBottom: 16 }}>
        <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>{title}</p>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 3 }}>{description}</p>
      </div>
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {children}
      </div>
    </div>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const [apiUrl, setApiUrl] = useState('http://localhost:8000')
  const [queryStale, setQueryStale] = useState('30')
  const [saved, setSaved] = useState(false)
  const [clearing, setClearing] = useState(false)

  function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  async function handleClearCache() {
    setClearing(true)
    await qc.invalidateQueries()
    await qc.resetQueries()
    setTimeout(() => setClearing(false), 800)
  }

  return (
    <div style={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: 20 }}>
      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <Section
          title="API Configuration"
          description="Configure how the frontend connects to the SSPM backend."
        >
          <div>
            <label className="label" htmlFor="api-url">Backend URL</label>
            <input
              id="api-url"
              type="text"
              className="input"
              style={{ fontFamily: 'monospace' }}
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="http://localhost:8000"
            />
            <p style={{ marginTop: 6, fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'flex-start', gap: 5 }}>
              <Info size={12} style={{ marginTop: 1, flexShrink: 0 }} />
              Requests are proxied through Vite at <code style={{ fontFamily: 'monospace' }}>/api</code>. Changing this requires restarting the dev server.
            </p>
          </div>

          <div>
            <label className="label" htmlFor="query-stale">Query refresh interval (seconds)</label>
            <input
              id="query-stale"
              type="number"
              min="10"
              max="3600"
              className="input"
              style={{ width: 120, fontFamily: 'monospace' }}
              value={queryStale}
              onChange={(e) => setQueryStale(e.target.value)}
            />
            <p style={{ marginTop: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              How often queries refresh in the background. Default: 30s.
            </p>
          </div>
        </Section>

        <Section
          title="Appearance"
          description="Customize the look and feel of the SSPM dashboard."
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)' }}>Dark mode</p>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                Toggle using the button in the sidebar footer.
              </p>
            </div>
            <span style={{ borderRadius: 6, background: 'var(--surface-2)', padding: '4px 10px', fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)' }}>
              sspm-theme
            </span>
          </div>
        </Section>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button type="submit" className="btn-primary">
            <Save size={14} />
            {saved ? 'Saved!' : 'Save Settings'}
          </button>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Settings are stored locally only</span>
        </div>
      </form>

      <Section
        title="Data & Cache"
        description="Manage the local query cache used by TanStack Query."
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <p style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--text)' }}>Clear query cache</p>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>Forces all queries to re-fetch from the API.</p>
          </div>
          <button onClick={handleClearCache} disabled={clearing} className="btn-ghost" style={{ border: '1px solid var(--border)' }}>
            {clearing ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <RefreshCw size={14} />}
            Clear Cache
          </button>
        </div>
      </Section>

      <Section title="About" description="SSPM platform information.">
        <dl style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
          {[
            ['Version', '0.1.0'],
            ['Framework', 'React 18 + Vite + TypeScript'],
            ['UI', 'TailwindCSS v3 + CSS Variables'],
            ['Data fetching', 'TanStack Query v5'],
            ['API', '/api/v1 (proxied)'],
            ['Build tool', 'Vite 5'],
          ].map(([k, v]) => (
            <div key={k}>
              <dt style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>{k}</dt>
              <dd style={{ fontSize: '0.875rem', color: 'var(--text)', fontWeight: 500, marginTop: 2 }}>{v}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </div>
  )
}
