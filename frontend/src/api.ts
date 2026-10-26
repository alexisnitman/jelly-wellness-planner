import type { RoleQuestion, ExportRequest, CalendarRequest, CalendarResult, Interview, LinkStatus, Plan, ProposeRequest, Profile, RegisterInput, User } from './types'

export interface Health {
  ok: boolean
  ai_enabled: boolean
  model: string
  daily_cap_usd: number
  spent_today_usd: number
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin', // the session cookie is httpOnly; JavaScript never sees it
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const data = (await res.json()) as { detail?: string; errors?: { field: string; message: string }[] }
      if (data.errors?.length) msg = data.errors.map((e) => `${e.field}: ${e.message}`).join('. ')
      else if (data.detail) msg = data.detail
    } catch {
      /* keep the default message */
    }
    throw new ApiError(msg, res.status)
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

export const fetchHealth = () => request<Health>('GET', '/api/health')

export const register = (input: RegisterInput) => request<User>('POST', '/api/auth/register', input)
export const login = (username: string, password: string) => request<User>('POST', '/api/auth/login', { username, password })
export const forgotPassword = (email: string) => request<{ message: string }>('POST', '/api/auth/forgot', { email })
export const resetPassword = (token: string, password: string) => request<{ ok: boolean }>('POST', '/api/auth/reset', { token, password })
export const logout = () => request<void>('POST', '/api/auth/logout')
export const fetchMe = () => request<User>('GET', '/api/auth/me')

export const fetchProfile = () => request<Profile>('GET', '/api/profile')
export const fetchRoleQuestions = () => request<Record<string, RoleQuestion[]>>('GET', '/api/profile/role-questions')
export const saveProfile = (p: Profile) => request<Profile>('PUT', '/api/profile', p)

export const readCalendar = (r: CalendarRequest) => request<CalendarResult>('POST', '/api/calendar/read', r)
export const fetchLinkStatus = () => request<LinkStatus>('GET', '/api/calendar/link')
export const forgetLink = () => request<LinkStatus>('DELETE', '/api/calendar/link')

export const fetchQuestions = (description: string) => request<Interview>('POST', '/api/interview/questions', { description })
export const prefetchPlan = (r: Pick<ProposeRequest, 'week_start' | 'class_request' | 'dinner_request' | 'movie_request'>) => request<{ started: string[] }>('POST', '/api/plan/prefetch', r)
export const proposePlan = (r: ProposeRequest) => request<Plan>('POST', '/api/plan/propose', r)

// The .ics comes back as a file; read it as a blob so the page can offer it as a download.
export async function exportPlan(r: ExportRequest): Promise<{ blob: Blob; filename: string }> {
  const res = await fetch('/api/plan/export', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(r),
  })
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const data = (await res.json()) as { detail?: string; errors?: { field: string; message: string }[] }
      msg = data.errors?.length ? data.errors.map((e) => `${e.field}: ${e.message}`).join('. ') : (data.detail ?? msg)
    } catch {
      /* keep the default message */
    }
    throw new ApiError(msg, res.status)
  }
  const m = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')
  return { blob: await res.blob(), filename: m?.[1] ?? 'week-plan.ics' }
}
