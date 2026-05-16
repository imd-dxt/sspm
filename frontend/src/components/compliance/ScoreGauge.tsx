interface ScoreGaugeProps {
  score: number
  size?: number
  label?: string
}

export function ScoreGauge({ score, size = 96, label }: Readonly<ScoreGaugeProps>) {
  const r = (size / 2) * 0.72
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - Math.max(0, Math.min(100, score)) / 100)
  const color =
    score >= 75 ? 'var(--ok)'
    : score >= 50 ? 'var(--sev-medium)'
    : 'var(--sev-critical)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      <svg width={size} height={size} style={{ flexShrink: 0 }}>
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke="color-mix(in oklch, var(--border) 140%, transparent)" strokeWidth={6}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={6}
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
        <text
          x={size / 2} y={size / 2 + 1}
          textAnchor="middle" dominantBaseline="middle"
          style={{ fill: color, fontSize: size * 0.22, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}
        >
          {score}%
        </text>
      </svg>
      {label && (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}>{label}</span>
      )}
    </div>
  )
}
