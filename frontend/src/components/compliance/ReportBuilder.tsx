import { useState } from 'react'
import { FileText, Download, Loader } from 'lucide-react'
import { useGenerateReport, useComplianceReports, type StoredReport } from '../../api/compliance'
import { useQueryClient } from '@tanstack/react-query'
import { formatRelative } from '../../lib/utils'

const PDF_BASE = '/api/v1'

const PLATFORMS = ['github', 'entra', 'jira', 'slack']
const FRAMEWORKS = ['CIS', 'SOC2', 'ISO27001', 'NIST-CSF']

export function ReportBuilder() {
  const [platform, setPlatform] = useState(PLATFORMS[0])
  const [framework, setFramework] = useState(FRAMEWORKS[0])
  const [withAI, setWithAI] = useState(true)

  const qc = useQueryClient()
  const generate = useGenerateReport()
  const { data: reports } = useComplianceReports()

  function handleGenerate() {
    generate.mutate(
      { platform, framework, with_ai_narrative: withAI },
      { onSuccess: () => qc.invalidateQueries({ queryKey: ['compliance', 'reports'] }) },
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Builder form */}
      <div className="card" style={{ padding: 24 }}>
        <h3 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: 16, color: 'var(--text)' }}>
          Generate New Report
        </h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>Platform</span>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontSize: '0.8125rem' }}
            >
              {PLATFORMS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 500 }}>Framework</span>
            <select
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
              style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', fontSize: '0.8125rem' }}
            >
              {FRAMEWORKS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={withAI}
              onChange={(e) => setWithAI(e.target.checked)}
            />
            <span style={{ fontSize: '0.8125rem', color: 'var(--text)' }}>AI narrative</span>
          </label>

          <button
            onClick={handleGenerate}
            disabled={generate.isPending}
            className="btn-primary btn-sm"
          >
            {generate.isPending ? <Loader size={13} className="animate-spin" /> : <FileText size={13} />}
            {generate.isPending ? 'Generating…' : 'Generate'}
          </button>
        </div>

        {generate.isSuccess && (
          <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: 8, background: 'color-mix(in oklch, var(--ok) 10%, transparent)', fontSize: '0.8125rem', color: 'var(--ok)' }}>
            Report generated — score: {generate.data.score}%
          </div>
        )}
        {generate.isError && (
          <div style={{ marginTop: 16, padding: '10px 14px', borderRadius: 8, background: 'color-mix(in oklch, var(--sev-critical) 10%, transparent)', fontSize: '0.8125rem', color: 'var(--sev-critical)' }}>
            {generate.error instanceof Error ? generate.error.message : 'Generation failed'}
          </div>
        )}
      </div>

      {/* Reports list */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>Generated Reports</h3>
        </div>
        {!reports?.length ? (
          <p style={{ padding: '24px 20px', fontSize: '0.8125rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            No reports yet. Generate one above.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {reports.map((r) => (
              <ReportRow key={r.id} report={r} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ReportRow({ report }: Readonly<{ report: StoredReport }>) {
  const [expanded, setExpanded] = useState(false)
  const score = report.score
  const color = score >= 75 ? 'var(--ok)' : score >= 50 ? 'var(--sev-medium)' : 'var(--sev-critical)'
  const pdfUrl = `${PDF_BASE}/compliance/reports/${report.id}/pdf`

  return (
    <div style={{ borderBottom: '1px solid var(--border)' }}>
      <div style={{ padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ fontSize: '1rem', fontWeight: 700, color, fontVariantNumeric: 'tabular-nums', minWidth: 48 }}>
          {score}%
        </span>
        <button
          onClick={() => setExpanded((e) => !e)}
          style={{ flex: 1, textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
        >
          <span style={{ fontSize: '0.8125rem', fontWeight: 500, color: 'var(--text)' }}>
            {report.platform} · {report.framework}
          </span>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: 10 }}>
            {formatRelative(report.created_at)}
          </span>
        </button>
        <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', flexShrink: 0 }}>
          {report.passed_rules}/{report.total_rules} rules
        </span>
        <a
          href={pdfUrl}
          download
          title="Download PDF"
          style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.75rem', color: 'var(--accent)', textDecoration: 'none', flexShrink: 0 }}
        >
          <Download size={13} /> PDF
        </a>
      </div>
      {expanded && report.ai_narrative && (
        <div style={{ padding: '12px 20px 16px', fontSize: '0.8125rem', color: 'var(--text)', lineHeight: 1.6, whiteSpace: 'pre-wrap', borderTop: '1px solid var(--border)' }}>
          {report.ai_narrative}
        </div>
      )}
    </div>
  )
}
