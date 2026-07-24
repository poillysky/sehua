import { Navigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import {
  clearSession,
  fetchAuthStatus,
  getCachedUser,
  getToken,
  setCachedUser,
  type AuthUser,
} from '../api/auth'
import { AppShell } from './AppShell'

/**
 * iOS 主屏幕全屏（standalone）离开几秒再回来常整页重载。
 * 必须先用本地 token+缓存用户乐观进入，再后台核对；
 * 仅当服务端明确 authenticated=false 才踢登录。
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

    // 已有本地会话：先展示，再静默校验（全屏回前台不闪登录页）
    if (token && localUser) {
      setUser(localUser)
      setOk(true)
      setReady(true)
    } else if (!token) {
      setOk(false)
      setUser(null)
      setReady(true)
      setHint('未登录或登录已过期')
      return () => {
        cancelled = true
      }
    } else {
      setReady(false)
      setHint('检查登录状态…')
    }

    fetchAuthStatus()
      .then((status) => {
        if (cancelled) return
        if (!status.auth_required) {
          setOk(true)
          setUser(status.user || localUser)
          return
        }
        if (status.authenticated && status.user) {
          setCachedUser(status.user)
          setUser(status.user)
          setOk(true)
          return
        }
        // 明确未登录：清本地并踢出
        clearSession()
        setOk(false)
        setUser(null)
        setHint('未登录或登录已过期')
      })
      .catch(() => {
        if (cancelled) return
        // 网络抖动：有 token 就不踢（主屏幕全屏回前台常见）
        if (token) {
          setOk(true)
          if (localUser) setUser(localUser)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅挂载/重试时检查
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
