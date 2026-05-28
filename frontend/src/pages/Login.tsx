import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, Eye, EyeOff, Loader } from 'lucide-react'
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
      setError(err instanceof ApiError && err.status === 401
        ? 'Invalid username or password.'
        : 'Could not reach the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 24,
    }}>
      <div style={{ width: '100%', maxWidth: 400, display: 'flex', flexDirection: 'column', gap: 0 }}>

        {/* Brand header */}
        <div style={{
          background: '#0B0875', borderRadius: '12px 12px 0 0',
          padding: '28px 32px 24px', textAlign: 'center',
        }}>
          <div style={{
            width: 52, height: 52, borderRadius: '50%',
            background: 'rgba(255,255,255,0.12)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 14px',
          }}>
            <ShieldCheck size={26} style={{ color: '#fff' }} />
          </div>
          <p style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff', lineHeight: 1 }}>SSPMer</p>
          <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.55)', marginTop: 6 }}>
            SaaS Security Posture Management
          </p>
        </div>

        {/* Form card */}
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderTop: 'none', borderRadius: '0 0 12px 12px',
          padding: '28px 32px',
          boxShadow: '0 8px 32px rgba(0,0,0,0.08)',
        }}>
          <p style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>
            Sign in
          </p>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 22 }}>
            Administrator access only
          </p>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Username */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
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
                  padding: '9px 12px', borderRadius: 8, fontSize: '0.875rem',
                  border: '1px solid var(--border)', background: 'var(--surface-2)',
                  color: 'var(--text)', outline: 'none', width: '100%',
                  boxSizing: 'border-box',
                }}
                onFocus={(e) => { e.target.style.borderColor = '#0B0875' }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)' }}
              />
            </div>

            {/* Password */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>
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
                    padding: '9px 40px 9px 12px', borderRadius: 8, fontSize: '0.875rem',
                    border: '1px solid var(--border)', background: 'var(--surface-2)',
                    color: 'var(--text)', outline: 'none', width: '100%',
                    boxSizing: 'border-box',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = '#0B0875' }}
                  onBlur={(e) => { e.target.style.borderColor = 'var(--border)' }}
                />
                <button
                  type="button"
                  onClick={() => setShowPwd((v) => !v)}
                  tabIndex={-1}
                  style={{
                    position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', padding: 2, display: 'flex',
                  }}
                >
                  {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Error message */}
            {error && (
              <p style={{
                fontSize: '0.75rem', color: 'var(--sev-critical)',
                background: 'color-mix(in oklch, var(--sev-critical) 8%, transparent)',
                padding: '8px 12px', borderRadius: 7,
              }}>
                {error}
              </p>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !username.trim() || !password}
              style={{
                marginTop: 4, padding: '10px 0', borderRadius: 8,
                background: '#0B0875', color: '#fff', fontWeight: 700,
                fontSize: '0.875rem', border: 'none', cursor: 'pointer',
                opacity: loading || !username.trim() || !password ? 0.5 : 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                transition: 'opacity 0.15s',
              }}
            >
              {loading && <Loader size={14} className="animate-spin" />}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>

      </div>
    </div>
  )
}
