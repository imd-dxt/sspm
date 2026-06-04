export interface Connector {
  id: string
  platform_name: 'github' | 'jira' | 'salesforce' | 'entraid'
  display_name: string
  is_active: boolean
  created_at: string
  updated_at: string
  connection_ok: boolean | null
  last_sync_at: string | null
  last_sync_error: string | null
  sync_interval_minutes: number | null
}

export interface ConnectorCreate {
  platform_name: string
  display_name: string
  credentials: Record<string, string>
  config: Record<string, unknown>
}

export interface ConnectorStatusResponse {
  connector_id: string
  connection_ok: boolean | null
  last_sync_at: string | null
  last_sync_error: string | null
  status: string
}

export interface ConnectorTestResponse {
  ok: boolean
  message?: string
  error?: string
  [key: string]: unknown
}

export interface Finding {
  id: number
  rule_id: string
  rule_name: string | null
  platform: string
  connector_id: string | null
  connector_name: string | null
  resource_type: string | null
  resource_identifier: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  category: string
  description: string
  status: 'open' | 'resolved' | 'false_positive' | 'accepted_risk'
  justification: string | null
  status_changed_at: string | null
  first_detected: string | null
  last_detected: string | null
  resolved_at: string | null
  remediation: string | null
  compliance_mapping: (string | Record<string, string>)[]
  // Ollama posture analysis
  impact_factor: number | null
  impact_explanation: string | null
  impact_source: string | null
  generated_remediation: string | null
  remediation_source: string | null
  // LLM judge (existing)
  llm_severity: string | null
  llm_severity_reasoning: string | null
  llm_exploitability: string | null
  llm_remediation: string | null
  llm_confidence: number | null
  llm_analyzed_at: string | null
  evidence?: Record<string, unknown>
}

export interface FindingSummary {
  total: number
  open_by_severity: { critical: number; high: number; medium: number; low: number }
  by_status: Record<string, number>
}

export interface FindingsQuery {
  severity?: string
  status?: string
  platform?: string
  connector_id?: string
  rule_id?: string
  category?: string
  limit?: number
  offset?: number
}

export interface UpdateFindingStatus {
  status: 'open' | 'resolved' | 'false_positive' | 'accepted_risk'
  justification?: string
}

export interface Rule {
  id: string
  name: string
  platform: string
  severity: string
  category: string
  description: string
  remediation: string
  detection_query: string
  query_type: string
  compliance_mapping: (string | Record<string, string>)[]
  referentials: string[]
  is_active: boolean
  cis_control: string | null
  profile: string | null
  rationale: string | null
}

export interface ScanRun {
  id: string
  connector_id: string
  status: string
  started_at: string | null
  completed_at: string | null
  records_fetched: number
  findings_count: number
  connection_ok: boolean | null
  errors: Array<Record<string, unknown>>
}

export interface ApiError {
  detail?: string
  message?: string
  [key: string]: unknown
}

// ── SaaS Identities ──────────────────────────────────────────────────────────

export interface IdentityPlatform {
  platform: string
  connector_id: string
  connector_name: string
  connection_ok: boolean | null
  last_sync_at: string | null
  user_count: number
  resource_count: number
}

export interface IdentitySummary {
  total_users: number
  total_admins: number
  users_at_risk: number
  total_resources: number
}

export interface IdentityResource {
  resource_id: string
  resource_name: string
  role: string
}

export interface IdentityUser {
  id: number
  platform_id: string
  username: string
  display_name: string
  email: string | null
  is_active: boolean
  is_external: boolean
  is_admin: boolean
  finding_count: number
  resource_count: number
  resources: IdentityResource[]
}

export interface FindingByResource {
  resource_identifier: string
  resource_type: string | null
  total: number
  critical: number
  high: number
  medium: number
  low: number
}

export interface IdentityResourceRow {
  id: number
  platform_id: string
  name: string
  resource_type: string | null
  finding_count: number
  critical: number
  high: number
  medium: number
  low: number
}

export interface IdentityGraphNode {
  id: string
  type: 'user' | 'resource' | 'group'
  platform_id: string
  label: string
  email?: string | null
  is_admin?: boolean
}

export interface IdentityGraphEdge {
  source: string
  target: string
  role: string
}

export interface IdentityGraph {
  nodes: IdentityGraphNode[]
  edges: IdentityGraphEdge[]
}

export interface ActivityLogEntry {
  id: number
  connector_id: string
  platform: string
  actor: string | null
  action: string
  resource: string | null
  timestamp: string
}

export interface ActivityLogSummary {
  total: number
  by_platform: Record<string, number>
}

export interface PostureScore {
  score: number
  total_open_findings: number
  by_severity: { critical: number; high: number; medium: number; low: number }
  pending_ollama_analysis: number
  formula: string
  filters: { platform: string | null; connector_id: string | null }
}

export interface PrioritizedAction {
  rank: number
  finding_id: string
  rule_id: string
  title: string
  severity: string
  platform: string
  resource_identifier: string
  impact_factor: number
  impact_summary: string
  recommended_action: string
}

export interface PrioritizedActionsResponse {
  actions: PrioritizedAction[]
  total_open_findings: number
  posture_score: number
  source: 'ollama' | 'deterministic'
  generated_at: string
}
