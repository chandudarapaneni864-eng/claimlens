const BASE = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api').replace(/\/$/, '')
const STORE = 'claimlens.tokens'

let tokens = null
try { tokens = JSON.parse(localStorage.getItem(STORE)) } catch { tokens = null }

export function setTokens(next) {
  tokens = next
  if (next) localStorage.setItem(STORE, JSON.stringify(next))
  else localStorage.removeItem(STORE)
}
export const hasTokens = () => Boolean(tokens?.access)

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

const pretty = (key) => key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

function messageFrom(data) {
  if (!data) return 'Something went wrong. Try again.'
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return data.map(messageFrom).join(' ')
  if (data.detail) return data.detail
  const [key, value] = Object.entries(data)[0] || []
  if (!key) return 'Something went wrong. Try again.'
  const msg = Array.isArray(value) ? value[0] : typeof value === 'object' ? messageFrom(value) : value
  return key === 'non_field_errors' ? msg : `${pretty(key)}: ${msg}`
}

async function refreshAccess() {
  try {
    const res = await fetch(`${BASE}/auth/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: tokens.refresh }),
    })
    if (!res.ok) return false
    const data = await res.json()
    setTokens({ ...tokens, access: data.access })
    return true
  } catch {
    return false
  }
}

export async function api(path, { method = 'GET', body, form } = {}, retry = true) {
  const headers = {}
  if (tokens?.access) headers.Authorization = `Bearer ${tokens.access}`
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: payload })
  } catch {
    throw new ApiError(`Can't reach the server at ${BASE}. Check that Django is running.`, 0)
  }
  if (res.status === 401 && retry && tokens?.refresh && path !== '/auth/login/') {
    if (await refreshAccess()) return api(path, { method, body, form }, false)
  }
  if (res.status === 401 && path !== '/auth/login/') {
    setTokens(null)
    window.dispatchEvent(new Event('claimlens:logout'))
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(messageFrom(data), res.status, data)
  return data
}

export const get = (path) => api(path)
export const post = (path, body) => api(path, { method: 'POST', body })
export const patch = (path, body) => api(path, { method: 'PATCH', body })
export const del = (path) => api(path, { method: 'DELETE' })
export const upload = (path, form) => api(path, { method: 'POST', form })
