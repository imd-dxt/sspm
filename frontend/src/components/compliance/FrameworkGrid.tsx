import { CheckCircle2, XCircle, HelpCircle } from 'lucide-react'
import type { ComplianceStandard, ComplianceControl } from '../../api/compliance'

interface FrameworkGridProps {
  standard: ComplianceStandard
}

function StatusCell({ status }: Readonly<{ status: string }>) {
  if (status === 'pass')
    return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}><CheckCircle2 size={15} style={{ color: 'var(--ok)' }} /></div>
  if (status === 'fail')
    return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}><XCircle size={15} style={{ color: 'var(--sev-critical)' }} /></div>
  // not_applicable
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <HelpCircle size={15} style={{ color: 'var(--text-muted)' }} />
    </div>
  )
}

function ControlRow({ control }: Readonly<{ control: ComplianceControl }>) {
  const rowBg =
    control.status === 'pass'
      ? 'color-mix(in oklch, var(--ok) 6%, transparent)'
      : control.status === 'fail'
      ? 'color-mix(in oklch, var(--sev-critical) 6%, transparent)'
      : 'transparent'

  return (
    <tr style={{ background: rowBg }}>
      <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text)' }}>{control.name}</div>
        <div style={{ fontSize: '0.6875rem', fontFamily: 'monospace', color: 'var(--text-muted)', marginTop: 2 }}>
          {control.id}
        </div>
      </td>
      <td style={{ padding: '10px 14px', textAlign: 'center', borderBottom: '1px solid var(--border)' }}>
        <StatusCell status={control.status} />
      </td>
      <td style={{ padding: '10px 14px', textAlign: 'right', borderBottom: '1px solid var(--border)' }}>
        {control.open_findings > 0 ? (
          <span style={{ fontSize: '0.75rem', color: 'var(--sev-critical)', fontWeight: 600 }}>
            {control.open_findings} open
          </span>
        ) : (
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>—</span>
        )}
      </td>
    </tr>
  )
}

export function FrameworkGrid({ standard }: Readonly<FrameworkGridProps>) {
  if (!standard.total_controls) {
    return (
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic', padding: '20px 0' }}>
        No rules are mapped to {standard.name} yet.
      </p>
    )
  }

  const sorted = [...standard.controls].sort((a, b) => {
    const order = { fail: 0, unknown: 1, pass: 2 }
    return (order[a.status as keyof typeof order] ?? 1) - (order[b.status as keyof typeof order] ?? 1)
  })

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'var(--surface-2)' }}>
            <th style={{ padding: '8px 14px', textAlign: 'left', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)' }}>
              Control
            </th>
            <th style={{ padding: '8px 14px', textAlign: 'center', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', width: 80 }}>
              Status
            </th>
            <th style={{ padding: '8px 14px', textAlign: 'right', fontSize: '0.6875rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: '1px solid var(--border)', width: 100 }}>
              Findings
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <ControlRow key={c.id} control={c} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
