import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useComplianceTrends, type TrendPoint } from '../../api/compliance'
import { format } from 'date-fns'

const PALETTE = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

function buildChartData(points: TrendPoint[]): { date: string; [key: string]: string | number }[] {
  const byDate = new Map<string, Record<string, number>>()
  for (const p of points) {
    const date = format(new Date(p.snapshot_date), 'MM/dd HH:mm')
    if (!byDate.has(date)) byDate.set(date, {})
    const key = `${p.platform}·${p.framework}`
    byDate.get(date)![key] = p.score
  }
  return [...byDate.entries()].map(([date, vals]) => ({ date, ...vals }))
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

  const chartData = points ? buildChartData(points) : []
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
                dataKey="date"
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
