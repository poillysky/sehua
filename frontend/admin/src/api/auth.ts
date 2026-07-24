import { api, getToken, setToken } from './client'

export type AuthUser = {
  id: number
  username: string
  display_name?: string | null
  roles: string[]
  permissions?: string[]
  is_active?: boolean
}

export type AuthRole = {
  name: string
  label: string
  permissions: string[]
}

export type ManagedUser = {
  id: number
  username: string
  display_name: string | null
  is_active: boolean
  roles: string[]
  created_at: string | null
  last_login_at: string | null
}

export type AuthStatus = {
  auth_required: boolean
  authenticated: boolean
  has_users: boolean
  user: AuthUser | null
}

export async function fetchAuthStatus() {
  // 超时放宽：爬虫忙时 8s 不够，过短会让 RequireAuth 误判掉线（1.1.7 回归）
  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), 30000)
  try {
    const status = await api<AuthStatus & { token?: string }>('/api/auth/status', {
      signal: ctrl.signal,
    })
    // 后端滑动续期时同步本地 Bearer，避免旧 token 挡住 Cookie
    if (status.token) setToken(status.token)
    return status
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('后端无响应（可能正在爬帖占满），请稍后刷新或先停止爬虫')
    }
    throw err
  } finally {
    window.clearTimeout(timer)
  }
}

export async function login(username: string, password: string) {
  const data = await api<{ token: string; user: AuthUser; message: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  if (data.token) setToken(data.token)
  return data
}

export async function logout() {
  try {
    await api<{ message: string }>('/api/auth/logout', { method: 'POST' })
  } finally {
    setToken(null)
  }
}

export async function changePassword(currentPassword: string, newPassword: string) {
  return api<{ message: string }>('/api/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
}

export function fetchUsers() {
  return api<{ users: ManagedUser[]; roles: AuthRole[] }>('/api/auth/users')
}

export function createUser(body: {
  username: string
  password: string
  display_name?: string
  roles: string[]
}) {
  return api<{ message: string; user: AuthUser }>('/api/auth/users', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateUser(
  userId: number,
  body: {
    display_name?: string | null
    password?: string
    is_active?: boolean
    roles?: string[]
  },
) {
  return api<{ message: string; user: AuthUser }>(`/api/auth/users/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function deleteUser(userId: number) {
  return api<{ message: string }>(`/api/auth/users/${userId}`, {
    method: 'DELETE',
  })
}

export function canManageUsers(user: AuthUser | null | undefined) {
  if (!user) return false
  const perms = user.permissions || []
  return perms.includes('*') || perms.includes('users.manage') || (user.roles || []).includes('admin')
}

export function can(user: AuthUser | null | undefined, permission: string) {
  if (!user) return false
  const perms = user.permissions || []
  return perms.includes('*') || perms.includes(permission) || (user.roles || []).includes('admin')
}

export { getToken, setToken }
