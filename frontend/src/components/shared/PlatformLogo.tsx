/**
 * PlatformLogo – renders the real logo for each SaaS platform.
 * GitHub and Salesforce use the image files from /public/logos/.
 * Jira and Entra ID use inline SVG marks (no image available).
 */

function JiraMark() {
  return (
    <svg viewBox="0 0 32 32" fill="none" width="60%" height="60%" aria-hidden="true">
      <defs>
        <linearGradient id="jira-a" x1="21.6" y1="8.25" x2="12.5" y2="17.4" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0052CC" />
          <stop offset="100%" stopColor="#2684FF" />
        </linearGradient>
        <linearGradient id="jira-b" x1="10.6" y1="23.5" x2="19.6" y2="14.4" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#0052CC" />
          <stop offset="100%" stopColor="#2684FF" />
        </linearGradient>
      </defs>
      <path d="M16.09 2.5 7.14 11.46a1.22 1.22 0 0 0 0 1.72l6.66 6.66 2.29-2.29L10.57 12.3l7.87-7.87L16.09 2.5Z" fill="url(#jira-a)" />
      <path d="M16.09 29.5l8.95-8.96a1.22 1.22 0 0 0 0-1.72l-6.66-6.66-2.29 2.29 5.52 5.54-7.87 7.87 2.35 1.64Z" fill="url(#jira-b)" />
    </svg>
  )
}

function EntraIDMark() {
  return (
    <svg viewBox="0 0 18 18" fill="none" width="60%" height="60%" aria-hidden="true">
      <path d="M9 1.5 1.5 5.75v6.5L9 16.5l7.5-4.25v-6.5L9 1.5Z" fill="none" stroke="white" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M9 1.5v15M1.5 5.75 9 10l7.5-4.25" stroke="white" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  )
}

const PLATFORM_BG: Record<string, string> = {
  github:     '#24292e',
  jira:       '#fff',
  salesforce: '#fff',
  entraid:    '#0078d4',
  slack:      '#4a154b',
  google:     '#fff',
  microsoft:  '#0078d4',
}

interface Props {
  platform: string
  size?: number
}

export default function PlatformLogo({ platform, size = 34 }: Readonly<Props>) {
  const bg = PLATFORM_BG[platform] ?? 'var(--surface-2)'
  const radius = Math.round(size * 0.24)
  const borderStyle = (platform === 'jira' || platform === 'salesforce' || platform === 'google')
    ? '1px solid rgba(0,0,0,0.10)'
    : 'none'
  const padding = Math.round(size * 0.1)

  const baseStyle: React.CSSProperties = {
    width: size,
    height: size,
    minWidth: size,
    borderRadius: radius,
    background: bg,
    border: borderStyle,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    overflow: 'hidden',
    padding,
    boxSizing: 'border-box',
  }

  if (platform === 'github') {
    return (
      <span style={baseStyle}>
        <img
          src="/logos/github.png"
          alt="GitHub"
          style={{ width: '100%', height: '100%', objectFit: 'contain', filter: 'brightness(0) invert(1)' }}
        />
      </span>
    )
  }

  if (platform === 'salesforce') {
    return (
      <span style={baseStyle}>
        <img
          src="/logos/salesforce.png"
          alt="Salesforce"
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      </span>
    )
  }

  if (platform === 'jira') {
    return (
      <span style={{ ...baseStyle, background: '#fff' }}>
        <JiraMark />
      </span>
    )
  }

  if (platform === 'entraid') {
    return (
      <span style={baseStyle}>
        <img
          src="/logos/hps.png"
          alt="Microsoft Entra ID"
          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        />
      </span>
    )
  }

  // Unknown platform fallback
  return (
    <span style={{ ...baseStyle, background: 'var(--surface-2)' }}>
      <span style={{ fontSize: Math.round(size * 0.32), fontWeight: 700, color: 'var(--text-muted)', letterSpacing: '-0.01em' }}>
        {platform.slice(0, 2).toUpperCase()}
      </span>
    </span>
  )
}
