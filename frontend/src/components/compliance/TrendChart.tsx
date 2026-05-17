import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useComplianceTrends, type TrendPoint } from '../../api/compliance'
import { format } from 'date-fns'

const PALETTE = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

type ChartRow = { label: string; fullDate: string; [key: string]: string | number }

function buildChartData(points: TrendPoint[], singlePlatform: boolean): ChartRow[] {
  const hasScanIds = points.some((p) => p.scan_run_id)

  if (hasScanIds && singlePlatform) {
    // Group by scan_run_id — each sync = one x-axis point
    const byScan = new Map<string, { date: Date; scores: Record<string, number> }>()
    for (const p of points) {
      const key = p.scan_run_id!
      if (!byScan.has(key)) {
        byScan.set(key, { date: new Date(p.snapshot_date), scores: {} })
      }
      byScan.get(key)!.scores[`${p.platform}·${p.framework}`] = p.score
    }
    const sorted = [...byScan.entries()].sort((a, b) => a[1].date.getTime() - b[1].date.getTime())
    return sorted.map(([, val], idx) => ({
      label: `Sync ${idx + 1}`,
      fullDate: format(val.date, 'MM/dd HH:mm'),
      ...val.scores,
    }))
  }

  // Default: group by day
  const byDate = new Map<string, Record<string, number>>()
  for (const p of points) {
    const date = format(new Date(p.snapshot_date), 'MM/dd')
    if (!byDate.has(date)) byDate.set(date, {})
    byDate.get(date)![`${p.platform}·${p.framework}`] = p.score
  }
  return [...byDate.entries()].map(([date, vals]) => ({ label: date, fullDate: date, ...vals }))
}

function getSeriesKeys(points: TrendPoint[]): string[] {
  return [...new Set(points.map((p) => `${p.platform}·${p.framework}`))].sort()
}

export function TrendChart() {
  const [days, setDays] = useState(30)
  const [filterPlatform, setFilterPlatform] = useState('')
  const [filterFramework, setFilterFramework] = useState('')

  const { data: points, isLoading } = useComplianceTrends(
    filterPlatform || undefined,
    filterFramework || undefined,
    days,
  )

  const singlePlatform = !!filterPlatform
  const chartData = points ? buildChartData(points, singlePlatform) : []
  const seriesKeys = points ? getSeriesKeys(points) : []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Controls */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <select
          value={filterPlatform}
          onChange={(e) => setFilterPlatform(e.target.value)}
          style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontSize: '0.8125rem' }}
        >
          <option value="">All platforms</option>
          {['github', 'entra', 'jira', 'slack'].map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select
          value={filterFramework}
          onChange={(e) => setFilterFramework(e.target.value)}
          style={{ padding: '5px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontSize: '0.8125rem' }}
        >
          <option value="">All frameworks</option>
          {['CIS', 'SOC2', 'ISO27001', 'NIST-CSF'].map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <div style={{ display: 'flex', gap: 6 }}>
          {[7, 14, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={days === d ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
              style={{ fontSize: '0.75rem', padding: '4px 10px' }}
            >
              {d}d
            </button>
          ))}
        </div>
        {singlePlatform && points?.some((p) => p.scan_run_id) && (
          <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            · one point per sync
          </span>
        )}
      </div>

      {/* Chart */}
      <div className="card" style={{ padding: '20px 16px 12px' }}>
        {isLoading ? (
          <div className="skeleton" style={{ height: 300, borderRadius: 8 }} />
        ) : !chartData.length ? (
          <div style={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              No trend data yet. Snapshots are taken after each connector sync.
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: '0.75rem' }}
                formatter={(value) => [`${value}%`]}
                labelFormatter={(label, payload) => {
                  const row = payload?.[0]?.payload as ChartRow | undefined
                  return row?.fullDate && row.fullDate !== label ? `${label} — ${row.fullDate}` : label
                }}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem' }} />
              {seriesKeys.map((key, i) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={PALETTE[i % PALETTE.length]}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
