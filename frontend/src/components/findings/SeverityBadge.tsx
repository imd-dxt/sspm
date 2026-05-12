interface Props {
  readonly severity: string
  readonly className?: string
}

export default function SeverityBadge({ severity, className = '' }: Props) {
  const sev = severity.toLowerCase()
  const cls = ['critical', 'high', 'medium', 'low', 'info'].includes(sev) ? sev : 'info'
  return (
    <span className={`sev-badge sev-${cls} ${className}`}>
      {severity}
    </span>
  )
}
