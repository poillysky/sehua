import { useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { fetchAuthStatus, login } from '../api/auth'
import { toast } from '../ui/toast'

function safeReturnPath(from: unknown): string {
  if (typeof from !== 'string' || !from.startsWith('/') || from.startsWith('//')) {
    return '/resources'
  }
  return from === '/login' ? '/resources' : from
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const returnTo = safeReturnPath((location.state as { from?: string } | null)?.from)
  const [user, setUser] = useState('admin')
  const [pass, setPass] = useState('')
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const t = window.setTimeout(() => setReady(true), 30)
    return () => window.clearTimeout(t)
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchAuthStatus()
      .then((s) => {
        if (cancelled) return
        if (!s.auth_required || s.authenticated) {
          navigate(returnTo, { replace: true })
        }
      })
      .catch(() => {
        /* stay on login */
      })
    return () => {
      cancelled = true
    }
  }, [navigate, returnTo])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await login(user.trim(), pass)
      toast.success('登录成功')
      navigate(returnTo, { replace: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`login-page${ready ? ' is-ready' : ''}`}>
      <div className="login-atmosphere" aria-hidden>
        <div className="login-atmosphere-grid" />
        <div className="login-atmosphere-orb login-atmosphere-orb--a" />
        <div className="login-atmosphere-orb login-atmosphere-orb--b" />
        <div className="login-atmosphere-beam" />
      </div>

      <main className="login-shell">
        <header className="login-hero">
          <span className="login-mark" aria-hidden>
            <svg viewBox="0 0 48 48" fill="none">
              <path
                d="M24 4L8 13v22l16 9 16-9V13L24 4z"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
              <path
                d="M24 24l16-9M24 24v22M24 24L8 15"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <circle cx="24" cy="24" r="3.2" fill="currentColor" />
            </svg>
          </span>
          <p className="login-kicker">资源收集管理</p>
          <h1 className="login-brand">色花堂收集器</h1>
          <p className="login-lead">管理后台登录</p>
        </header>

        <form className="login-form" onSubmit={(e) => void onSubmit(e)}>
          <label className="login-field">
            <span className="login-field-lbl">用户名</span>
            <input
              value={user}
              onChange={(e) => setUser(e.target.value)}
              autoComplete="username"
              required
              autoFocus
              placeholder="请输入用户名"
            />
          </label>
          <label className="login-field">
            <span className="login-field-lbl">密码</span>
            <input
              type="password"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
              autoComplete="current-password"
              required
              minLength={1}
              placeholder="请输入密码"
            />
          </label>
          <button type="submit" className="login-submit" disabled={busy}>
            {busy ? '登录中…' : '进入后台'}
          </button>
        </form>

        <p className="login-foot">仅限授权账号访问</p>
      </main>
    </div>
  )
}
