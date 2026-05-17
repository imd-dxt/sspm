import { useState, useRef, useEffect } from 'react'
import { Bot, X, Send, Loader, ChevronDown, ShieldCheck, AlertTriangle } from 'lucide-react'
import { useAskCompliance, useComplianceReport, useComplianceScores, type AskResponse } from '../api/compliance'

interface Message {
  role: 'user' | 'assistant'
  text: string
  source?: string
}

const SUGGESTIONS = [
  'What are my most critical compliance gaps?',
  'How do I fix MFA in my GitHub org?',
  'How do I improve my CIS score?',
  'Am I audit-ready for SOC 2?',
]

function ScorePill({ label, score }: Readonly<{ label: string; score: number }>) {
  const color = score >= 75 ? 'var(--ok)' : score >= 50 ? 'var(--sev-medium)' : 'var(--sev-critical)'
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: '6px 10px', borderRadius: 8, background: 'var(--surface-2)',
      border: '1px solid var(--border)', minWidth: 64,
    }}>
      <span style={{ fontSize: '1rem', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>
        {score}%
      </span>
      <span style={{ fontSize: '0.5625rem', color: 'var(--text-muted)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {label}
      </span>
    </div>
  )
}

export function SSPMerChat() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const ask = useAskCompliance()

  const { data: overview } = useComplianceReport()
  const { data: scores } = useComplianceScores()

  // Summary stats for context strip
  const overallScore = overview?.overall_score ?? null
  const failingCount = overview?.standards.reduce((s, x) => s + x.failing_controls, 0) ?? 0
  const criticalStds = overview?.standards.filter((s) => s.score < 50 && s.total_controls > 0) ?? []
  const topScores = scores?.slice(0, 4) ?? []

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [messages, open])

  function send(question: string) {
    const q = question.trim()
    if (!q) return
    setMessages((m) => [...m, { role: 'user', text: q }])
    setInput('')
    ask.mutate(
      { question: q },
      {
        onSuccess: (data: AskResponse) =>
          setMessages((m) => [...m, { role: 'assistant', text: data.answer, source: data.source }]),
        onError: () =>
          setMessages((m) => [
            ...m,
            { role: 'assistant', text: 'Something went wrong. Please try again.', source: 'static' },
          ]),
      },
    )
  }

  return (
    <>
      {/* Chat panel */}
      {open && (
        <div style={{
          position: 'fixed', right: 24, bottom: 88, zIndex: 1000,
          width: 380, height: 560,
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 16, boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{
            padding: '12px 16px', borderBottom: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', gap: 10,
            background: 'var(--surface)', flexShrink: 0,
          }}>
            <div style={{
              width: 34, height: 34, borderRadius: '50%',
              background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <Bot size={18} style={{ color: '#fff' }} />
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text)', lineHeight: 1 }}>SSPMer</p>
              <p style={{ fontSize: '0.625rem', color: 'var(--ok)', marginTop: 2 }}>● AI Security Advisor</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4 }}
            >
              <ChevronDown size={16} />
            </button>
          </div>

          {/* Compliance context strip */}
          {overallScore !== null && messages.length === 0 && (
            <div style={{
              padding: '10px 14px', background: 'var(--surface-2)',
              borderBottom: '1px solid var(--border)', flexShrink: 0,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <ShieldCheck size={12} style={{ color: 'var(--accent)' }} />
                <span style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Current Posture
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <ScorePill label="Overall" score={overallScore} />
                {topScores.map((s) => (
                  <ScorePill key={`${s.platform}-${s.framework}`} label={s.framework} score={s.score} />
                ))}
              </div>
              {failingCount > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 8 }}>
                  <AlertTriangle size={11} style={{ color: 'var(--sev-critical)', flexShrink: 0 }} />
                  <span style={{ fontSize: '0.6875rem', color: 'var(--sev-critical)' }}>
                    {failingCount} failing control{failingCount > 1 ? 's' : ''}
                    {criticalStds.length > 0 && ` · ${criticalStds.map((s) => s.name).join(', ')} below 50%`}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            {messages.length === 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 4 }}>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', textAlign: 'center', marginBottom: 4 }}>
                  Ask me anything about your security posture.
                </p>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    style={{
                      textAlign: 'left', padding: '8px 12px', borderRadius: 10,
                      border: '1px solid var(--border)', background: 'var(--surface-2)',
                      color: 'var(--text)', fontSize: '0.75rem', cursor: 'pointer',
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: 'flex', gap: 8,
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                  alignItems: 'flex-end',
                }}
              >
                {msg.role === 'assistant' && (
                  <div style={{
                    width: 26, height: 26, borderRadius: '50%', background: 'var(--accent)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  }}>
                    <Bot size={13} style={{ color: '#fff' }} />
                  </div>
                )}
                <div style={{
                  maxWidth: '82%', padding: '8px 12px', fontSize: '0.8125rem', lineHeight: 1.6,
                  borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                  background: msg.role === 'user' ? 'var(--accent)' : 'var(--surface-2)',
                  color: msg.role === 'user' ? '#fff' : 'var(--text)',
                  whiteSpace: 'pre-wrap',
                }}>
                  {msg.text}
                  {msg.source === 'static' && (
                    <div style={{ fontSize: '0.5625rem', opacity: 0.55, marginTop: 3 }}>offline mode</div>
                  )}
                </div>
              </div>
            ))}

            {ask.isPending && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <div style={{
                  width: 26, height: 26, borderRadius: '50%', background: 'var(--accent)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Bot size={13} style={{ color: '#fff' }} />
                </div>
                <div style={{ background: 'var(--surface-2)', borderRadius: '14px 14px 14px 4px', padding: '10px 14px' }}>
                  <Loader size={13} style={{ color: 'var(--text-muted)' }} className="animate-spin" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)', display: 'flex', gap: 8, flexShrink: 0 }}>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send(input)}
              placeholder="Ask SSPMer…"
              disabled={ask.isPending}
              style={{
                flex: 1, padding: '8px 12px', borderRadius: 10, fontSize: '0.8125rem',
                border: '1px solid var(--border)', background: 'var(--surface-2)',
                color: 'var(--text)', outline: 'none',
              }}
            />
            <button
              onClick={() => send(input)}
              disabled={!input.trim() || ask.isPending}
              style={{
                width: 36, height: 36, borderRadius: '50%', background: 'var(--accent)',
                border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center',
                justifyContent: 'center', flexShrink: 0,
                opacity: !input.trim() || ask.isPending ? 0.45 : 1,
              }}
            >
              <Send size={14} style={{ color: '#fff' }} />
            </button>
          </div>
        </div>
      )}

      {/* Floating button */}
      <button
        onClick={() => setOpen((o) => !o)}
        title="SSPMer AI Assistant"
        style={{
          position: 'fixed', right: 24, bottom: 24, zIndex: 1001,
          width: 54, height: 54, borderRadius: '50%',
          background: 'var(--accent)', border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
          transition: 'transform 0.2s, box-shadow 0.2s',
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1.08)' }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.transform = 'scale(1)' }}
      >
        {open ? <X size={21} style={{ color: '#fff' }} /> : <Bot size={21} style={{ color: '#fff' }} />}
      </button>
    </>
  )
}
