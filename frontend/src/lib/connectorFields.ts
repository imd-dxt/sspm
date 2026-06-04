export type PlatformKey = 'github' | 'jira' | 'salesforce' | 'entraid'

export interface FieldDef {
  key: string
  label: string
  placeholder?: string
  hint?: string
  type?: 'text' | 'password' | 'textarea'
  isConfig?: boolean
}

export const PLATFORM_FIELDS: Record<PlatformKey, FieldDef[]> = {
  github: [
    {
      key: 'token',
      label: 'Personal Access Token',
      type: 'password',
      placeholder: 'ghp_xxxxxxxxxxxxxxxxxxxx',
      hint: 'GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic). Required scopes: read:org, repo',
    },
    {
      key: 'org',
      label: 'GitHub Organization',
      placeholder: 'my-org',
      hint: 'Your GitHub organization login (e.g. "acme-corp")',
      isConfig: true,
    },
  ],
  jira: [
    { key: 'email', label: 'Account Email', placeholder: 'you@company.com' },
    { key: 'api_token', label: 'API Token', placeholder: 'ATATT...', type: 'password' },
    { key: 'domain', label: 'Jira Domain', placeholder: 'mycompany.atlassian.net', isConfig: true },
  ],
  salesforce: [
    { key: 'username', label: 'Username', placeholder: 'admin@company.com' },
    { key: 'password', label: 'Password', type: 'password' },
    { key: 'security_token', label: 'Security Token', type: 'password' },
    { key: 'instance', label: 'Instance URL', placeholder: 'mycompany.my.salesforce.com', isConfig: true },
  ],
  entraid: [
    { key: 'tenant_id', label: 'Tenant ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', isConfig: true },
    { key: 'client_id', label: 'Client ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    { key: 'client_secret', label: 'Client Secret', type: 'password' },
  ],
}

/** Returns only the credentials fields (excluding isConfig items) for a platform. */
export function getCredentialFields(platform: string): FieldDef[] {
  const fields = PLATFORM_FIELDS[platform as PlatformKey]
  return fields ? fields.filter((f) => !f.isConfig) : []
}
