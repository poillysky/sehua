import { Navigate, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { fetchAuthStatus, type AuthUser } from '../api/auth'
import { AppShell } from './AppShell'

export function RequireAuth() {
  const location = useLocation()
  const [ready, setReady] = useState(false)
  const [ok, setOk] = useState(false)
  const [user, setUser] = useState<AuthUser | null>(null)
  const [hint, setHint] = useState('检查登录状态…')

  useEffect(() => {
    let cancelled = false
    setReady(false)
    setHint('检查登录状态…')
    fetchAuthStatus()
      .then((status) => {
        if (cancelled) return
        const allowed = !status.auth_required || status.authenticated
        setOk(allowed)
        setUser(status.user)
      })
      .catch((err) => {
        if (!cancelled) {
          setOk(false)
          setUser(null)
          setHint(err instanceof Error ? err.message : '检查登录失败')
        }
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [location.pathname])

  if (!ready) {
    return (
      <div className="login-page">
        <p className="hint">{hint}</p>
      </div>
    )
  }

  if (!ok || !user) {
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
