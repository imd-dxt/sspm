const BASE = '/api/v1'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function getToken(): string | null {
  return localStorage.getItem('sspm_token')
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function handleUnauthorized(url: string) {
  console.warn(`[Auth] 401 from ${url} — clearing token`)
  // Dispatch an event so the AuthProvider can update React state and let
  // <ProtectedRoute> redirect through React Router (no hard window reload).
  globalThis.dispatchEvent(new CustomEvent('auth:logout'))
}

async function parseResponse<T>(res: Response): Promise<T> {
  // Login endpoint returns 401 on bad credentials — DON'T treat that as a
  // session expiry. Only fire the logout flow for OTHER endpoints.
  const isLoginRequest = res.url.endsWith('/auth/login')

  if (res.status === 401 && !isLoginRequest) {
    handleUnauthorized(res.url)
    throw new ApiError(401, 'Session expired. Please log in again.', null)
  }

  const contentType = res.headers.get('content-type') ?? ''
  const isJson = contentType.includes('application/json')
  const body = isJson ? await res.json() : await res.text()

  if (res.ok) return body as T

  let message = `HTTP ${res.status}`
  if (isJson && typeof body === 'object' && body !== null) {
    const b = body as Record<string, unknown>
    message = (b['detail'] as string) ?? (b['message'] as string) ?? message
  } else if (typeof body === 'string' && body.length > 0) {
    message = body
  }
  throw new ApiError(res.status, message, body)
}

export async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  let url = `${BASE}${path}`
  if (params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    }
    const s = qs.toString()
    if (s) url += `?${s}`
  }
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  })
  return parseResponse<T>(res)
}

export async function post<T>(
  path: string,
  data?: unknown,
  params?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  let url = `${BASE}${path}`
  if (params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    }
    const s = qs.toString()
    if (s) url += `?${s}`
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: data !== undefined ? JSON.stringify(data) : undefined,
  })
  return parseResponse<T>(res)
}

export async function put<T>(path: string, data?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: data !== undefined ? JSON.stringify(data) : undefined,
  })
  return parseResponse<T>(res)
}

export async function patch<T>(path: string, data?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: data !== undefined ? JSON.stringify(data) : undefined,
  })
  return parseResponse<T>(res)
}

export async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
  })
  return parseResponse<T>(res)
}

/**
 * Authenticated file download. Fetches with the JWT header, then triggers
 * the browser download via a Blob URL. Needed because <a href="..."> cannot
 * attach an Authorization header — the server would return 401 and the
 * browser would show "file is not available".
 */
export async function downloadAuthed(path: string, filename: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { ...authHeaders() },
  })
  if (res.status === 401) {
    handleUnauthorized(res.url)
    throw new ApiError(401, 'Session expired. Please log in again.', null)
  }
  if (!res.ok) {
    let detail = `Download failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body === 'object' && body !== null && 'detail' in body) {
        detail = String((body as { detail: unknown }).detail)
      }
    } catch { /* body wasn't JSON */ }
    throw new ApiError(res.status, detail, null)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  // Defer revoke so the browser has time to start the download
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

/** Direct login call — uses no auth header (pre-auth) */
export async function loginRequest(username: string, password: string): Promise<{ access_token: string; username: string; expires_in: number }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  return parseResponse(res)
}
