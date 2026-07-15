import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import type { AuthUser } from '../api/auth'
import { can, changePassword, logout } from '../api/auth'
import { fetchHealth, type HealthDb } from '../api/health'
import { toast } from '../ui/toast'

const MAIN_NAV = [
  { to: '/resources', label: '处理记录', short: '记录', icon: IconList },
  { to: '/crawler', label: '爬虫状态', short: '爬虫', icon: IconSpider },
  { to: '/parse-test', label: '解析测试', short: '解析', icon: IconLink },
  { to: '/data', label: '数据管理', short: '数据', icon: IconDb, permission: 'settings.write' },
] as const

type Props = {
  user: AuthUser
}

type DbState = 'checking' | 'ok' | 'down'

export function AppShell({ user }: Props) {
  const navigate = useNavigate()
  const label = user.display_name || user.username
  const avatar = (label || '?').slice(0, 1).toUpperCase()
  const [dbState, setDbState] = useState<DbState>('checking')
  const [dbInfo, setDbInfo] = useState<HealthDb | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [pwdOpen, setPwdOpen] = useState(false)
  const [currentPass, setCurrentPass] = useState('')
  const [newPass, setNewPass] = useState('')
  const [confirmPass, setConfirmPass] = useState('')
  const [pwdError, setPwdError] = useState('')
  const [pwdBusy, setPwdBusy] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const data = await fetchHealth()
        if (cancelled) return
        setDbInfo(data.db)
        setDbState(data.db?.ok ? 'ok' : 'down')
      } catch {
        if (cancelled) return
        setDbInfo(null)
        setDbState('down')
      }
    }

    void check()
    const timer = window.setInterval(() => void check(), 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (!menuOpen) return

    function onPointerDown(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setMenuOpen(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  async function onLogout() {
    setMenuOpen(false)
    await logout()
    navigate('/login', { replace: true })
  }

  function openChangePassword() {
    setMenuOpen(false)
    setCurrentPass('')
    setNewPass('')
    setConfirmPass('')
    setPwdError('')
    setPwdOpen(true)
  }

  async function onChangePassword(e: FormEvent) {
    e.preventDefault()
    setPwdError('')
    if (newPass.length < 6) {
      setPwdError('新密码至少 6 位')
      return
    }
    if (newPass !== confirmPass) {
      setPwdError('两次输入的新密码不一致')
      return
    }
    setPwdBusy(true)
    try {
      await changePassword(currentPass, newPass)
      setCurrentPass('')
      setNewPass('')
      setConfirmPass('')
      setPwdOpen(false)
      toast.success('密码已修改')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '修改失败')
    } finally {
      setPwdBusy(false)
    }
  }

  const pillClass =
    dbState === 'ok' ? 'health-pill badge badge-ok' : dbState === 'down' ? 'health-pill badge badge-down' : 'health-pill badge badge-muted'

  const pillText = dbState === 'checking' ? '检查库…' : dbState === 'ok' ? '库已连接' : '库离线'

  const pillTitle = dbInfo
    ? dbInfo.ok
      ? `${dbInfo.host}:${dbInfo.port}/${dbInfo.name} (${dbInfo.backend})`
      : dbInfo.error || '数据库不可用'
    : dbState === 'checking'
      ? '正在检测数据库'
      : '无法访问 /health'

  const navItems = MAIN_NAV.filter((item) => !('permission' in item) || can(user, item.permission))

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <button type="button" className="header-brand" onClick={() => navigate('/resources')}>
            <span className="brand-mark" aria-hidden>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                <path d="M12 2L4 6.5v11L12 22l8-4.5v-11L12 2z" />
                <path d="M12 12l8-4.5M12 12v10M12 12L4 7.5" />
              </svg>
            </span>
            <span className="brand-title">色花堂收集器</span>
          </button>

          <nav className="header-nav main-nav desktop-only" aria-label="主导航">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'nav-btn active' : 'nav-btn')}>
                <item.icon />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="header-actions">
          <span className={pillClass} title={pillTitle}>
            <span className="health-dot" />
            <span>{pillText}</span>
          </span>
          <span className="header-sep" aria-hidden />
          <NavLink to="/settings" className={({ isActive }) => (isActive ? 'nav-btn icon-btn active' : 'nav-btn icon-btn')} title="系统设置">
            <IconGear />
            <span className="nav-label desktop-inline">设置</span>
          </NavLink>

          <div className={`user-menu ${menuOpen ? 'open' : ''}`} ref={menuRef}>
            <button
              type="button"
              className="user-chip"
              title="账号菜单"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              aria-controls={menuId}
              onClick={() => setMenuOpen((v) => !v)}
            >
              <span className="user-avatar">{avatar}</span>
              <span className="user-name">{label}</span>
              <span className="user-caret" aria-hidden>
                ▾
              </span>
            </button>

            {menuOpen ? (
              <div className="user-dropdown" id={menuId} role="menu">
                <div className="user-dropdown-head">
                  <span className="user-avatar lg">{avatar}</span>
                  <div className="user-dropdown-meta">
                    <strong>{label}</strong>
                  </div>
                </div>
                <div className="user-dropdown-sep" />
                <button type="button" className="user-dropdown-item" role="menuitem" onClick={openChangePassword}>
                  <IconKey />
                  <span>修改密码</span>
                </button>
                <div className="user-dropdown-sep" />
                <button type="button" className="user-dropdown-item danger" role="menuitem" onClick={() => void onLogout()}>
                  <IconLogout />
                  <span>退出登录</span>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      <div className="app-body">
        <Outlet context={{ user }} />
      </div>

      {pwdOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => !pwdBusy && setPwdOpen(false)}>
          <div
            className="modal-card card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="change-pwd-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3 id="change-pwd-title">修改密码</h3>
              <button type="button" className="btn ghost sm icon-only" title="关闭" disabled={pwdBusy} onClick={() => setPwdOpen(false)}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <form className="modal-body" onSubmit={(e) => void onChangePassword(e)}>
              <label className="parse-test-field">
                <span className="lbl">当前密码</span>
                <input
                  type="password"
                  value={currentPass}
                  onChange={(e) => setCurrentPass(e.target.value)}
                  autoComplete="current-password"
                  required
                  autoFocus
                />
              </label>
              <label className="parse-test-field">
                <span className="lbl">新密码</span>
                <input
                  type="password"
                  value={newPass}
                  onChange={(e) => setNewPass(e.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={6}
                />
              </label>
              <label className="parse-test-field">
                <span className="lbl">确认新密码</span>
                <input
                  type="password"
                  value={confirmPass}
                  onChange={(e) => setConfirmPass(e.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={6}
                />
              </label>
              {pwdError ? <p className="hint warn">{pwdError}</p> : null}
              <div className="modal-actions">
                <button type="button" className="btn ghost sm" disabled={pwdBusy} onClick={() => setPwdOpen(false)}>
                  取消
                </button>
                <button type="submit" className="btn primary sm" disabled={pwdBusy}>
                  {pwdBusy ? '提交中…' : '确认修改'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      <nav className="bottomnav mobile-only" aria-label="底部导航">
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={({ isActive }) => (isActive ? 'bnav-item active' : 'bnav-item')}>
            <item.icon />
            <span>{item.short}</span>
          </NavLink>
        ))}
        <NavLink to="/settings" className={({ isActive }) => (isActive ? 'bnav-item active' : 'bnav-item')}>
          <IconGear />
          <span>设置</span>
        </NavLink>
      </nav>
    </div>
  )
}

function IconList() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 6h16M4 12h16M4 18h10" />
    </svg>
  )
}
function IconSpider() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  )
}
function IconLink() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  )
}
function IconDb() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
      <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
    </svg>
  )
}
function IconGear() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  )
}
function IconKey() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
    </svg>
  )
}
function IconLogout() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </svg>
  )
}
