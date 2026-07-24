import { Navigate, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { fetchAuthStatus, getToken, type AuthUser } from '../api/auth'
import { AppShell } from './AppShell'

/**
 * 登录门禁。
 *
 * 1.1.7 起每次切页都重查 /status，并在超时后当成未登录 → 手机/爬虫忙时被踢。
 * 这里只在挂载时查一次；切页不重查、不卸载 AppShell。
 */
export function RequireAuth() {
  const location = useLocation()
  const [ready, setReady] = useState(false)
  const [ok, setOk] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [hint, setHint] = useState('检查登录状态…')
  const [retryTick, setRetryTick] = useState(0)
  const checkedRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    setHint('检查登录状态…')

    fetchAuthStatus()
      .then((status) => {
        if (cancelled) return
        const allowed = !status.auth_required || status.authenticated
        setOk(allowed)
        setUser(status.user)
        checkedRef.current = true
        if (!allowed) setHint('未登录或登录已过期')
      })
      .catch((err) => {
        if (cancelled) return
        // 网络抖动：本地仍有 token 时不踢登录（手机断网/后端忙常见）
        if (getToken()) {
          if (!checkedRef.current) {
            setHint(err instanceof Error ? err.message : '检查登录失败，可重试')
            setOk(false)
            setUser(null)
          }
          return
        }
        setOk(false)
        setUser(null)
        setHint(err instanceof Error ? err.message : '检查登录失败')
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
    if (getToken() && hint && !hint.includes('未登录')) {
      return (
        <div className="login-page">
          <p className="hint">{hint}</p>
          <button type="button" className="btn" onClick={() => setRetryTick((n) => n + 1)}>
            重试
          </button>
        </div>
      )
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
