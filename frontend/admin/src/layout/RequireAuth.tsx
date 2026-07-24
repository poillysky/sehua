import { Navigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import {
  clearSession,
  fetchAuthStatus,
  getCachedUser,
  getToken,
  setCachedUser,
  setToken,
  type AuthUser,
} from '../api/auth'
import { AppShell } from './AppShell'

/**
 * 登录门禁。
 *
 * 注意：不能「本地无 token 就立刻 /login」。
 * iOS 全屏 / Lucky HTTPS 下常见 Cookie 仍有效但 localStorage 空，
 * 立刻踢登录会与 LoginPage「已登录则跳回」形成 replaceState 死循环。
 */
export function RequireAuth() {
  const location = useLocation()
  const cached = getCachedUser()
  const hasToken = Boolean(getToken())
  const [ready, setReady] = useState(() => Boolean(hasToken && cached))
  const [ok, setOk] = useState(() => Boolean(hasToken && cached))
  const [user, setUser] = useState<AuthUser | null>(() => (hasToken ? cached : null))
  const [hint, setHint] = useState('检查登录状态…')
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    const token = getToken()
    const localUser = getCachedUser()

    if (token && localUser) {
      setUser(localUser)
      setOk(true)
      setReady(true)
    } else {
      setReady(false)
      setHint('检查登录状态…')
    }

    fetchAuthStatus()
      .then((status) => {
        if (cancelled) return
        if (!status.auth_required) {
          const u = status.user || localUser
          if (u) {
            setCachedUser(u)
            setUser(u)
            setOk(true)
          } else {
            setOk(false)
            setUser(null)
            setHint('未登录或登录已过期')
          }
          return
        }
        if (status.authenticated && status.user) {
          setCachedUser(status.user)
          setUser(status.user)
          setOk(true)
          // Cookie 会话有效时补齐本地缓存，避免再次被误判未登录
          if (!getToken() && (status as { token?: string }).token) {
            setToken((status as { token?: string }).token || null)
          }
          return
        }
        clearSession()
        setOk(false)
        setUser(null)
        setHint('未登录或登录已过期')
      })
      .catch(() => {
        if (cancelled) return
        if (token && localUser) {
          setOk(true)
          setUser(localUser)
          return
        }
        setOk(false)
        setUser(null)
        setHint('检查登录失败，可重试')
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })

    return () => {
      cancelled = true
    }
  }, [retryTick])

  if (!ready) {
    return (
      <div className="login-page">
        <p className="hint">{hint}</p>
      </div>
    )
  }

  if (!ok || !user) {
    if (hint && !hint.includes('未登录')) {
      return (
        <div className="login-page">
          <p className="hint">{hint}</p>
          <button type="button" className="btn" onClick={() => setRetryTick((n) => n + 1)}>
            重试
          </button>
        </div>
      )
    }
    // 已在登录页时不要再 Navigate，避免 replace 风暴
    if (location.pathname === '/login') {
      return null
    }
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    )
  }

  return <AppShell user={user} />
}
