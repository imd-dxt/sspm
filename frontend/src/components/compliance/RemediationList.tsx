import { useState } from 'react'
import { Wrench, ChevronDown, ChevronRight, Loader, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useGetAIFix } from '../../api/compliance'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../api/client'

interface FindingItem {
  id: number
  rule_id: string
  rule_name?: string
  severity: string
  description: string
  platform: string
  resource_name?: string
  resource_identifier: string
  status: string
  remediation?: string
}

const SEV_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 }
const SEV_COLOR: Record<string, string> = {
  critical: 'var(--sev-critical)',
  high: 'var(--sev-high)',
  medium: 'var(--sev-medium)',
  low: 'var(--sev-low)',
}

function FindingCard({ finding }: Readonly<{ finding: FindingItem }>) {
  const [expanded, setExpanded] = useState(false)
  const [fix, setFix] = useState<string | null>(null)
  const getAIFix = useGetAIFix()

  function handleGetFix() {
    getAIFix.mutate(finding.id, {
      onSuccess: (data) => setFix(data.suggestion),
    })
  }

  const sevColor = SEV_COLOR[finding.severity] ?? 'var(--text-muted)'

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div
        style={{ padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer' }}
        onClick={() => setExpanded((e) => !e)}
      >
        <AlertTriangle size={15} style={{ color: sevColor, flexShrink: 0, marginTop: 2 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>{finding.description}</span>
            <span style={{
              fontSize: '0.625rem', fontWeight: 700, padding: '1px 6px', borderRadius: 8,
              background: `color-mix(in oklch, ${sevColor} 15%, transparent)`,
              color: sevColor, textTransform: 'uppercase',
            }}>
              {finding.severity}
            </span>
          </div>
          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 3 }}>
            {finding.platform} · {finding.resource_name ?? finding.resource_identifier}
          </div>
        </div>
        {expanded ? <ChevronDown size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} /> : <ChevronRight size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
      </div>

      {expanded && (
        <div style={{ padding: '0 16px 14px', display: 'flex', flexDirection: 'column', gap: 10, borderTop: '1px solid var(--border)' }}>
          {fix ? (
            <div style={{ padding: '10px 14px', borderRadius: 8, background: 'color-mix(in oklch, var(--ok) 8%, transparent)', fontSize: '0.8125rem', color: 'var(--text)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6, color: 'var(--ok)', fontWeight: 600, fontSize: '0.75rem' }}>
                <CheckCircle2 size={13} /> AI Remediation
              </div>
              {fix}
            </div>
          ) : (
            finding.remediation && (
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                {finding.remediation}
              </p>
            )
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleGetFix}
              disabled={getAIFix.isPending || !!fix}
              className="btn-ghost btn-sm"
            >
              {getAIFix.isPending ? <Loader size={12} className="animate-spin" /> : <Wrench size={12} />}
              {fix ? 'Fix shown above' : 'Get AI fix'}
            </button>
          </div>
          {getAIFix.isError && (
            <p style={{ fontSize: '0.75rem', color: 'var(--sev-critical)' }}>
              {getAIFix.error instanceof Error ? getAIFix.error.message : 'Failed to get fix'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function RemediationList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['findings', 'open-remediation'],
    queryFn: () => get<FindingItem[]>('/findings/', { status: 'open', limit: 50 }),
    staleTime: 60_000,
  })

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[1, 2, 3].map((i) => <div key={i} className="skeleton" style={{ height: 60, borderRadius: 10 }} />)}
      </div>
    )
  }

  if (error || !data) {
    return (
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
        Could not load findings.
      </p>
    )
  }

  const sorted = [...(data ?? [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  )

  if (!sorted.length) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '40px 0' }}>
        <CheckCircle2 size={28} style={{ color: 'var(--ok)' }} />
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>No open findings — great posture!</p>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        {sorted.length} open finding{sorted.length !== 1 ? 's' : ''}, sorted by severity. Click to expand and get AI-assisted remediation.
      </p>
      {sorted.map((f) => <FindingCard key={f.id} finding={f} />)}
    </div>
  )
}
