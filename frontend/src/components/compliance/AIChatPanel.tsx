import { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, Loader } from 'lucide-react'
import { useAskCompliance, type AskResponse } from '../../api/compliance'

interface Message {
  role: 'user' | 'assistant'
  text: string
  source?: 'ollama' | 'static'
}

const SUGGESTIONS = [
  'What are the most critical compliance gaps?',
  'How do I improve my CIS Benchmark score?',
  'What does SOC 2 CC6.1 require?',
  'Which controls are failing on GitHub?',
]

export function AIChatPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [platform, setPlatform] = useState('')
  const [framework, setFramework] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const ask = useAskCompliance()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function send(question: string) {
    if (!question.trim()) return
    const q = question.trim()
    setMessages((m) => [...m, { role: 'user', text: q }])
    setInput('')
    ask.mutate(
      { question: q, ...(platform && { platform }), ...(framework && { framework }) },
      {
        onSuccess: (data: AskResponse) => {
          setMessages((m) => [...m, { role: 'assistant', text: data.answer, source: data.source }])
        },
        onError: () => {
          setMessages((m) => [...m, { role: 'assistant', text: 'Failed to get a response. Please try again.', source: 'static' }])
        },
      },
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 12 }}>
      {/* Context filters */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontSize: '0.8125rem' }}
        >
          <option value="">All platforms</option>
          {['github', 'entra', 'jira', 'slack'].map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <select
          value={framework}
          onChange={(e) => setFramework(e.target.value)}
          style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontSize: '0.8125rem' }}
        >
          <option value="">All frameworks</option>
          {['CIS', 'SOC2', 'ISO27001', 'NIST-CSF'].map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
      </div>

      {/* Messages */}
      <div className="card" style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 300, maxHeight: 480 }}>
        {messages.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
            <Bot size={28} style={{ color: 'var(--text-muted)' }} />
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', textAlign: 'center' }}>
              Ask a compliance question or choose a suggestion:
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="btn-ghost btn-sm"
                  style={{ fontSize: '0.75rem' }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 10,
                alignItems: 'flex-start',
                flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              }}
            >
              <div style={{
                width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                background: msg.role === 'user' ? 'var(--accent)' : 'var(--surface-2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {msg.role === 'user'
                  ? <User size={14} style={{ color: '#fff' }} />
                  : <Bot size={14} style={{ color: 'var(--text-muted)' }} />
                }
              </div>
              <div style={{
                maxWidth: '78%',
                padding: '10px 14px',
                borderRadius: msg.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
                background: msg.role === 'user' ? 'var(--accent)' : 'var(--surface-2)',
                fontSize: '0.8125rem',
                color: msg.role === 'user' ? '#fff' : 'var(--text)',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
              }}>
                {msg.text}
                {msg.source === 'static' && (
                  <div style={{ marginTop: 4, fontSize: '0.6875rem', opacity: 0.6 }}>AI unavailable · static response</div>
                )}
              </div>
            </div>
          ))
        )}
        {ask.isPending && (
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--surface-2)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={14} style={{ color: 'var(--text-muted)' }} />
            </div>
            <Loader size={16} style={{ color: 'var(--text-muted)' }} className="animate-spin" />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send(input)}
          placeholder="Ask about your compliance posture…"
          disabled={ask.isPending}
          style={{
            flex: 1, padding: '9px 14px', borderRadius: 10,
            border: '1px solid var(--border)', background: 'var(--surface)',
            color: 'var(--text)', fontSize: '0.8125rem',
          }}
        />
        <button
          onClick={() => send(input)}
          disabled={!input.trim() || ask.isPending}
          className="btn-primary btn-sm"
          style={{ padding: '9px 14px' }}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  )
}
