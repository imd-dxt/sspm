import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Loader } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { loginRequest, ApiError } from '../api/client'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!username.trim() || !password) return
    setError('')
    setLoading(true)
    try {
      const data = await loginRequest(username.trim(), password)
      login(data.access_token, data.username)
      navigate('/', { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'Invalid username or password.'
          : 'Could not reach the server. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      background: 'var(--bg)',
    }}>

      {/* ── Left panel: logo ───────────────────────────────────────────── */}
      <div style={{
        flex: '0 0 55%',
        background: '#0B0875',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 64px',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* Subtle background decoration */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(ellipse at 60% 40%, rgba(74,143,232,0.12) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />

        {/* SSPM SVG logo */}
        <div style={{ width: '100%', maxWidth: 380, position: 'relative', zIndex: 1 }}>
          <img
            src="/sspm_logo.svg"
            alt="SSPM"
            style={{ width: '100%', height: 'auto', display: 'block' }}
          />
        </div>

        {/* Tagline below logo */}
        <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', marginTop: 8 }}>
          <p style={{
            fontSize: '1rem', color: 'rgba(255,255,255,0.55)',
            letterSpacing: '0.04em', fontWeight: 400,
          }}>
            SaaS Security Posture Management
          </p>
          <p style={{
            fontSize: '0.75rem', color: 'rgba(255,255,255,0.3)',
            marginTop: 6, letterSpacing: '0.02em',
          }}>
            Automated compliance · Real-time risk · AI-driven insights
          </p>
        </div>

      </div>

      {/* ── Right panel: login form ────────────────────────────────────── */}
      <div style={{
        flex: '0 0 45%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-start',
        padding: '48px 56px',
        background: 'var(--surface)',
      }}>
        <div style={{ width: '100%', maxWidth: 460 }}>

          {/* Header */}
          <div style={{ marginBottom: 36 }}>
            <p style={{
              fontSize: '1.75rem', fontWeight: 700,
              color: 'var(--text)', lineHeight: 1.15, marginBottom: 8,
            }}>
              Sign in
            </p>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Sign in to access the platform.
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

            {/* Username */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{
                fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text)',
              }}>
                Username
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                disabled={loading}
                placeholder="admin"
                style={{
                  padding: '11px 14px', borderRadius: 9, fontSize: '0.9375rem',
                  border: '1.5px solid var(--border)', background: 'var(--surface-2)',
                  color: 'var(--text)', outline: 'none', width: '100%',
                  boxSizing: 'border-box', transition: 'border-color 0.15s',
                }}
                onFocus={(e) => { e.target.style.borderColor = '#0B0875' }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)' }}
              />
            </div>

            {/* Password */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{
                fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text)',
              }}>
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPwd ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={loading}
                  style={{
                    padding: '11px 44px 11px 14px', borderRadius: 9, fontSize: '0.9375rem',
                    border: '1.5px solid var(--border)', background: 'var(--surface-2)',
                    color: 'var(--text)', outline: 'none', width: '100%',
                    boxSizing: 'border-box', transition: 'border-color 0.15s',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = '#0B0875' }}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--border)' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPwd((v) => !v)}
                  tabIndex={-1}
                  style={{
                    position: 'absolute', right: 12, top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', padding: 2,
                    display: 'flex', alignItems: 'center',
                  }}
                >
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <p style={{
                fontSize: '0.8125rem', color: 'var(--sev-critical)',
                background: 'color-mix(in oklch, var(--sev-critical) 8%, transparent)',
                padding: '10px 14px', borderRadius: 8, margin: 0,
              }}>
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !username.trim() || !password}
              style={{
                marginTop: 6, padding: '13px 0', borderRadius: 9,
                background: '#0B0875', color: '#fff', fontWeight: 700,
                fontSize: '0.9375rem', border: 'none', cursor: 'pointer',
                opacity: loading || !username.trim() || !password ? 0.5 : 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                transition: 'opacity 0.15s, background 0.15s',
                letterSpacing: '0.01em',
              }}
              onMouseEnter={(e) => {
                if (!loading && username.trim() && password)
                  e.currentTarget.style.background = '#0e0fa8'
              }}
              onMouseLeave={(e) => { e.currentTarget.style.background = '#0B0875' }}
            >
              {loading && <Loader size={15} className="animate-spin" />}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>

          </form>

          {/* Footer note */}
          <p style={{
            marginTop: 32, fontSize: '0.6875rem',
            color: 'var(--text-muted)', lineHeight: 1.6,
          }}>
            This platform is restricted to authorised personnel only.
            Unauthorised access attempts are logged and monitored.
          </p>
        </div>
      </div>

    </div>
  )
}
