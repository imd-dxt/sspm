import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  type TooltipProps,
} from 'recharts'
import type { FindingSummary } from '../../api/types'
import { formatNumber, severityColor } from '../../lib/utils'

interface Props {
  summary: FindingSummary
}

const SEV_KEYS: Array<keyof FindingSummary['open_by_severity']> = [
  'critical',
  'high',
  'medium',
  'low',
]

function CustomTooltip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null
  const item = payload[0]
  if (!item) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-md">
      <span className="font-medium text-text capitalize">{item.name}</span>
      <span className="ml-2 tabular-nums text-muted">{formatNumber(item.value as number)}</span>
    </div>
  )
}

export default function DonutChart({ summary }: Props) {
  const data = SEV_KEYS.filter((k) => summary.open_by_severity[k] > 0).map((k) => ({
    name: k,
    value: summary.open_by_severity[k],
    color: severityColor(k),
  }))

  const total = data.reduce((s, d) => s + d.value, 0)

  if (total === 0) {
    return (
      <div className="flex h-48 flex-col items-center justify-center text-center">
        <div
          className="mb-2 flex h-10 w-10 items-center justify-center rounded-full text-lg"
          style={{ background: 'var(--sev-ok)', opacity: 0.2 }}
        />
        <p className="text-sm font-medium text-sev-ok">No open findings</p>
        <p className="text-xs text-muted mt-1">All clear</p>
      </div>
    )
  }

  return (
    <div className="relative flex items-center gap-6">
      <div className="relative h-48 w-48 flex-shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={88}
              paddingAngle={2}
              dataKey="value"
              strokeWidth={0}
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        {/* Center label */}
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold tabular-nums text-text">
            {formatNumber(total)}
          </span>
          <span className="text-xs text-muted">open</span>
        </div>
      </div>

      {/* Legend */}
      <ul className="space-y-2">
        {data.map((d) => (
          <li key={d.name} className="flex items-center gap-2 text-sm">
            <span
              className="h-2.5 w-2.5 flex-shrink-0 rounded-full"
              style={{ background: d.color }}
            />
            <span className="capitalize text-muted w-16">{d.name}</span>
            <span className="tabular-nums font-medium text-text">{formatNumber(d.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
