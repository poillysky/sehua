import {
  api,
  clearSession,
  getCachedUser,
  getToken,
  setCachedUser,
  setToken,
} from './client'

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

export function fetchAuthStatus() {
  // 不要 AbortController：超时会误踢；全屏回前台靠 Cookie/本地缓存恢复
  return api<AuthStatus & { token?: string }>('/api/auth/status').then((status) => {
    if (status.token) setToken(status.token)
    if (status.user) setCachedUser(status.user)
    return status
  })
}

export async function login(username: string, password: string) {
  const data = await api<{ token: string; user: AuthUser; message: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  if (data.token) setToken(data.token)
  if (data.user) setCachedUser(data.user)
  return data
}

export async function logout() {
  try {
    await api<{ message: string }>('/api/auth/logout', { method: 'POST' })
  } finally {
    clearSession()
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

export { getToken, setToken, getCachedUser, setCachedUser, clearSession }
