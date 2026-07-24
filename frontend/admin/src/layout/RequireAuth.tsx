import { Navigate, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import { fetchAuthStatus, type AuthUser } from '../api/auth'
import { AppShell } from './AppShell'

function isTransientAuthError(err: unknown): boolean {
  if (!(err instanceof Error)) return false
  const msg = err.message || ''
  // 1.1.7 起 status 有 8s 超时；爬虫占满时会 abort，不能当成掉线
  if (err.name === 'AbortError') return true
  if (msg.includes('后端无响应') || msg.includes('AbortError')) return true
  if (/failed to fetch|networkerror|load failed|网络连接失败/i.test(msg)) return true
  return false
}

export function RequireAuth() {
  const location = useLocation()
  const [ready, setReady] = useState(false)
  const [ok, setOk] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [hint, setHint] = useState('检查登录状态…')
  const [retryTick, setRetryTick] = useState(0)
  const authedRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    const soft = authedRef.current
    if (!soft) {
      setReady(false)
      setHint('检查登录状态…')
    }

    fetchAuthStatus()
      .then((status) => {
        if (cancelled) return
        const allowed = !status.auth_required || status.authenticated
        setOk(allowed)
        setUser(status.user)
        authedRef.current = Boolean(allowed && status.user)
        if (!allowed) setHint('未登录或登录已过期')
      })
      .catch((err) => {
        if (cancelled) return
        // 已登录会话：短暂超时/网络抖动只提示，不踢回登录页
        if (authedRef.current && isTransientAuthError(err)) {
          setHint(err instanceof Error ? err.message : '检查登录失败')
          return
        }
        setOk(false)
        setUser(null)
        authedRef.current = false
        setHint(err instanceof Error ? err.message : '检查登录失败')
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })

    return () => {
      cancelled = true
    }
  }, [location.pathname, retryTick])

  if (!ready) {
    return (
      <div className="login-page">
        <p className="hint">{hint}</p>
      </div>
    )
  }

  if (!ok || !user) {
    // 首次检查因后端忙失败：留在门禁页可重试，避免误当成「掉线」
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
