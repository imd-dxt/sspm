import { cn } from '../../lib/utils'

interface SeverityData {
  critical: number
  high: number
  medium: number
  low: number
}

interface Props {
  data: SeverityData
  className?: string
  showLabels?: boolean
}

const SEV_CONFIG = [
  { key: 'critical' as const, var: '--sev-critical', label: 'C' },
  { key: 'high' as const, var: '--sev-high', label: 'H' },
  { key: 'medium' as const, var: '--sev-medium', label: 'M' },
  { key: 'low' as const, var: '--sev-low', label: 'L' },
]

export default function SeverityBars({ data, className, showLabels = true }: Props) {
  const total = data.critical + data.high + data.medium + data.low
  if (total === 0) {
    return (
      <div className={cn('flex items-center gap-1', className)}>
        <div className="h-2 flex-1 rounded-full" style={{ background: 'var(--border)' }} />
        {showLabels && <span className="text-xs text-muted">None</span>}
      </div>
    )
  }

  return (
    <div className={cn('space-y-1.5', className)}>
      {showLabels && (
        <div className="flex gap-0.5 overflow-hidden rounded-md h-2">
          {SEV_CONFIG.map(({ key, var: cssVar }) => {
            const pct = (data[key] / total) * 100
            if (pct === 0) return null
            return (
              <div
                key={key}
                className="h-full transition-all"
                style={{ width: `${pct}%`, background: `var(${cssVar})` }}
                title={`${key}: ${data[key]}`}
              />
            )
          })}
        </div>
      )}
      <div className="flex items-center gap-3">
        {SEV_CONFIG.map(({ key, var: cssVar, label }) => (
          <div key={key} className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: `var(${cssVar})` }}
            />
            <span className="text-xs text-muted">{label}</span>
            <span
              className="text-xs font-medium tabular-nums"
              style={{ color: `var(${cssVar})` }}
            >
              {data[key]}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
