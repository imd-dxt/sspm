import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { formatDistanceToNow, format, isAfter, subDays } from 'date-fns'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatRelative(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return '—'
    const sevenDaysAgo = subDays(new Date(), 7)
    if (isAfter(date, sevenDaysAgo)) {
      return formatDistanceToNow(date, { addSuffix: true })
    }
    return format(date, 'MMM d, yyyy')
  } catch {
    return '—'
  }
}

export function formatAbsolute(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return '—'
    return format(date, 'MMM d, yyyy HH:mm')
  } catch {
    return '—'
  }
}

export function formatNumber(n: number): string {
  if (n >= 10_000) return new Intl.NumberFormat('en', { notation: 'compact' }).format(n)
  return new Intl.NumberFormat('en').format(n)
}

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export function severityColor(sev: string): string {
  const map: Record<string, string> = {
    critical: 'var(--sev-critical)',
    high: 'var(--sev-high)',
    medium: 'var(--sev-medium)',
    low: 'var(--sev-low)',
    info: 'var(--sev-low)',
  }
  return map[sev.toLowerCase()] ?? 'var(--text-muted)'
}

export function severityBg(sev: string): string {
  const map: Record<string, string> = {
    critical: 'bg-sev-critical/15 text-sev-critical',
    high: 'bg-sev-high/15 text-sev-high',
    medium: 'bg-sev-medium/15 text-sev-medium',
    low: 'bg-sev-low/15 text-sev-low',
    info: 'bg-sev-low/10 text-sev-low',
  }
  return map[sev.toLowerCase()] ?? 'bg-muted/10 text-muted'
}

export function statusBg(status: string): string {
  const map: Record<string, string> = {
    open: 'bg-sev-high/15 text-sev-high',
    resolved: 'bg-sev-ok/15 text-sev-ok',
    false_positive: 'bg-muted/15 text-muted',
    accepted_risk: 'bg-sev-medium/15 text-sev-medium',
  }
  return map[status] ?? 'bg-muted/10 text-muted'
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    open: 'Open',
    resolved: 'Resolved',
    false_positive: 'False positive',
    accepted_risk: 'Accepted risk',
  }
  return map[status] ?? status
}

export const PLATFORMS: Record<string, { label: string; kind: string; abbr: string }> = {
  github: { label: 'GitHub', kind: 'Source code & repos', abbr: 'GH' },
  jira: { label: 'Jira', kind: 'Project management', abbr: 'JI' },
  salesforce: { label: 'Salesforce', kind: 'CRM & customer data', abbr: 'SF' },
  entraid: { label: 'Microsoft Entra ID', kind: 'Identity & access', abbr: 'EA' },
}

export function platformLabel(name: string): string {
  return PLATFORMS[name]?.label ?? name
}

export function calcPostureScore(summary: {
  open_by_severity: { critical: number; high: number; medium: number; low: number }
}): number {
  const { critical, high, medium, low } = summary.open_by_severity
  const penalty = critical * 4 + high * 3 + medium * 2 + low * 1
  return Math.max(0, 100 - penalty)
}
