/** HTTP helpers shared by auth / resources APIs. */
const TOKEN_KEY = 'collector_token'
const USER_KEY = 'collector_user'

const CJK_RE = /[\u4e00-\u9fff]/

const ERROR_MAP: Array<[RegExp | string, string]> = [
  [/notimplemented/i, '浏览器引擎无法启动（当前事件循环不支持启动子进程）。请重启后端后再试'],
  [/browser bootstrap failed/i, '论坛进站失败：所有入口均未能完成浏览器初始化'],
  [/r18\/safe shell/i, '仍卡在十八禁/安全浏览壳，无法进入论坛'],
  [/r18 block/i, '十八禁门拦截未解除，无法读取帖子'],
  [/cf challenge|cf persists|cloudflare/i, 'Cloudflare 人机验证未通过，请稍后重试或更换代理'],
  [/empty page/i, '页面内容为空，可能被拦截或站点异常'],
  [/target closed|browser has been closed/i, '浏览器会话已关闭，请重试'],
  [/executable doesn't exist/i, '未找到浏览器内核，请执行：playwright install chromium'],
  [/timed?\s*out|timeout/i, '请求超时，请检查网络或代理后重试'],
  [/connection refused|connecterror|getaddrinfo|name or service not known/i, '网络连接失败，请检查网络、入口域名或代理'],
  [/ssl|certificate/i, 'SSL/证书校验失败，请检查代理或站点证书'],
  [/request failed/i, '请求失败，请检查网络或代理后重试'],
  [/^HTTP\s+\d+/i, '服务请求失败'],
  [/field required|value error/i, '请求参数无效'],
]

function looksChinese(text: string) {
  return CJK_RE.test(text)
}

export function localizeErrorMessage(raw: unknown, fallback = '操作失败，请稍后重试'): string {
  if (raw == null) return fallback
  if (typeof raw !== 'string') {
    try {
      return localizeErrorMessage(JSON.stringify(raw), fallback)
    } catch {
      return fallback
    }
  }
  const text = raw.trim()
  if (!text) return fallback
  if (looksChinese(text)) return text
  for (const [needle, zh] of ERROR_MAP) {
    if (typeof needle === 'string' ? text.toLowerCase().includes(needle) : needle.test(text)) {
      return zh
    }
  }
  if (text.length <= 160) return `请求失败：${text}`
  return fallback
}

function formatApiDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return localizeErrorMessage(detail, fallback)
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === 'object' && 'msg' in item) {
        const loc = Array.isArray((item as { loc?: unknown }).loc)
          ? ((item as { loc: unknown[] }).loc.filter((p) => p !== 'body') as Array<string | number>)
          : []
        const field = loc.join('.')
        const msg = localizeErrorMessage(String((item as { msg: unknown }).msg || ''), '参数无效')
        return field ? `${field}：${msg}` : msg
      }
      return localizeErrorMessage(String(item), '')
    }).filter(Boolean)
    return parts.length ? parts.join('；') : fallback
  }
  if (detail && typeof detail === 'object') {
    const obj = detail as Record<string, unknown>
    const msg = obj.msg ?? obj.message ?? obj.detail
    if (msg != null) return localizeErrorMessage(String(msg), fallback)
  }
  return localizeErrorMessage(String(detail), fallback)
}

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key) || sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (!value) {
      localStorage.removeItem(key)
      sessionStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, value)
    sessionStorage.setItem(key, value)
  } catch {
    /* iOS 全屏/私密模式可能拒写，忽略 */
  }
}

export function getToken(): string | null {
  return readStorage(TOKEN_KEY)
}

export function setToken(token: string | null) {
  writeStorage(TOKEN_KEY, token)
}

export type CachedAuthUser = {
  id: number
  username: string
  display_name?: string | null
  roles: string[]
  permissions?: string[]
  is_active?: boolean
}

export function getCachedUser(): CachedAuthUser | null {
  const raw = readStorage(USER_KEY)
  if (!raw) return null
  try {
    const u = JSON.parse(raw) as CachedAuthUser
    if (!u || typeof u.id !== 'number' || !u.username) return null
    return u
  } catch {
    return null
  }
}

export function setCachedUser(user: CachedAuthUser | null) {
  writeStorage(USER_KEY, user ? JSON.stringify(user) : null)
}

/** 仅登出或确认会话失效时调用；接口 401 不要自动清（iOS 全屏回前台易误伤） */
export function clearSession() {
  setToken(null)
  setCachedUser(null)
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json')
  }
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(path, {
    ...init,
    headers,
    credentials: 'include',
  })

  if (res.status === 401) {
    // Cookie 重试；成功前绝不 clearSession（全屏 PWA 回前台常短暂丢 Cookie）
    const alreadyRetried = headers.get('X-Auth-Retry') === '1'
    if (token && !alreadyRetried) {
      const retryHeaders = new Headers(init.headers)
      if (!retryHeaders.has('Content-Type') && init.body) {
        retryHeaders.set('Content-Type', 'application/json')
      }
      retryHeaders.set('X-Auth-Retry', '1')
      retryHeaders.delete('Authorization')
      const retry = await fetch(path, {
        ...init,
        headers: retryHeaders,
        credentials: 'include',
      })
      if (retry.ok) {
        if (retry.status === 204) return undefined as T
        return (await retry.json()) as T
      }
      if (retry.status !== 401) {
        let detail: unknown = `HTTP ${retry.status}`
        try {
          const data = await retry.json()
          detail = data.detail ?? data.message ?? detail
        } catch {
          /* ignore */
        }
        throw new Error(formatApiDetail(detail, `请求失败（${retry.status}）`))
      }
    }
    // 保留本地 token，由 RequireAuth / 登出决定是否清会话
    throw new Error('未登录或登录已过期')
  }

  if (!res.ok) {
    let detail: unknown = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail ?? data.message ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(formatApiDetail(detail, `请求失败（${res.status}）`))
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}
