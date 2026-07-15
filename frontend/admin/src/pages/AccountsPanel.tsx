import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  canManageUsers,
  createUser,
  deleteUser,
  fetchUsers,
  updateUser,
  type AuthRole,
  type AuthUser,
  type ManagedUser,
} from '../api/auth'
import { confirmDialog } from '../ui/confirm'
import { toast } from '../ui/toast'

type Props = {
  currentUser: AuthUser
}

type EditorMode = 'create' | 'edit' | null

type FormState = {
  username: string
  displayName: string
  password: string
  role: string
  isActive: boolean
}

const EMPTY_FORM: FormState = {
  username: '',
  displayName: '',
  password: '',
  role: 'viewer',
  isActive: true,
}

function formatTime(value: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { hour12: false })
}

function roleLabel(roles: AuthRole[], name: string) {
  return roles.find((r) => r.name === name)?.label || name
}

export function AccountsPanel({ currentUser }: Props) {
  const manage = canManageUsers(currentUser)
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [roles, setRoles] = useState<AuthRole[]>([])
  const [loading, setLoading] = useState(manage)
  const [busyId, setBusyId] = useState<number | 'new' | null>(null)

  const [mode, setMode] = useState<EditorMode>(null)
  const [editing, setEditing] = useState<ManagedUser | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [formError, setFormError] = useState('')

  const load = useCallback(async () => {
    if (!manage) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const data = await fetchUsers()
      setUsers(data.users || [])
      setRoles(data.roles || [])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载用户失败')
      setUsers([])
    } finally {
      setLoading(false)
    }
  }, [manage])

  useEffect(() => {
    void load()
  }, [load])

  function openCreate() {
    setMode('create')
    setEditing(null)
    const defaultRole = roles.some((r) => r.name === 'viewer') ? 'viewer' : roles[0]?.name || 'viewer'
    setForm({ ...EMPTY_FORM, role: defaultRole })
    setFormError('')
  }

  function openEdit(user: ManagedUser) {
    setMode('edit')
    setEditing(user)
    setForm({
      username: user.username,
      displayName: user.display_name || '',
      password: '',
      role: user.roles?.[0] || 'viewer',
      isActive: user.is_active,
    })
    setFormError('')
  }

  function closeEditor() {
    if (busyId !== null) return
    setMode(null)
    setEditing(null)
    setFormError('')
  }

  function selectRole(name: string) {
    setForm((prev) => ({ ...prev, role: name }))
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError('')
    if (!form.role) {
      setFormError('请选择角色')
      return
    }

    if (mode === 'create') {
      if (form.username.trim().length < 2) {
        setFormError('用户名至少 2 位')
        return
      }
      if (form.password.length < 6) {
        setFormError('密码至少 6 位')
        return
      }
      setBusyId('new')
      try {
        await createUser({
          username: form.username.trim(),
          password: form.password,
          display_name: form.displayName.trim() || form.username.trim(),
          roles: [form.role],
        })
        toast.success('已创建用户')
        setMode(null)
        await load()
      } catch (err) {
        setFormError(err instanceof Error ? err.message : '创建失败')
      } finally {
        setBusyId(null)
      }
      return
    }

    if (mode === 'edit' && editing) {
      if (form.password && form.password.length < 6) {
        setFormError('新密码至少 6 位')
        return
      }
      setBusyId(editing.id)
      try {
        await updateUser(editing.id, {
          display_name: form.displayName.trim() || editing.username,
          roles: [form.role],
          is_active: form.isActive,
          ...(form.password ? { password: form.password } : {}),
        })
        toast.success('已保存用户')
        setMode(null)
        await load()
      } catch (err) {
        setFormError(err instanceof Error ? err.message : '保存失败')
      } finally {
        setBusyId(null)
      }
    }
  }

  async function onToggleActive(user: ManagedUser) {
    if (user.id === currentUser.id) {
      toast.warn('不能禁用当前登录账号')
      return
    }
    setBusyId(user.id)
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      toast.success(user.is_active ? `已禁用 ${user.username}` : `已启用 ${user.username}`)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '更新失败')
    } finally {
      setBusyId(null)
    }
  }

  async function onDelete(user: ManagedUser) {
    if (user.id === currentUser.id) {
      toast.warn('不能删除当前登录账号')
      return
    }
    const ok = await confirmDialog({
      title: '删除用户',
      message: `确定删除用户「${user.username}」？此操作不可恢复。`,
      confirmText: '删除',
      danger: true,
    })
    if (!ok) return
    setBusyId(user.id)
    try {
      await deleteUser(user.id)
      toast.success(`已删除 ${user.username}`)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="settings-panel active">
      <header className="settings-panel-head">
        <div>
          <h3>账号管理</h3>
          <p className="settings-panel-desc">管理系统登录账号与角色权限分配</p>
        </div>
        {manage ? (
          <div className="settings-panel-actions">
            <button type="button" className="btn secondary sm" onClick={() => void load()} disabled={loading || busyId !== null}>
              刷新
            </button>
            <button type="button" className="btn primary sm" onClick={openCreate} disabled={busyId !== null}>
              新增用户
            </button>
          </div>
        ) : null}
      </header>

      <div className="settings-panel-body">
        <div className="settings-card">
          <div className="settings-card-head">
            <h4>当前会话</h4>
          </div>
          <div className="settings-card-body">
            <div className="session-fields">
              <label>
                用户名
                <input value={currentUser.username} readOnly />
              </label>
              <label>
                显示名
                <input value={currentUser.display_name || currentUser.username} readOnly />
              </label>
              <label>
                角色
                <input value={(currentUser.roles || []).join('、') || '—'} readOnly />
              </label>
            </div>
          </div>
        </div>

        {!manage ? (
          <div className="settings-card">
            <div className="settings-card-body">
              <p className="hint warn">当前账号没有用户管理权限（需要 users.manage）。</p>
            </div>
          </div>
        ) : (
          <div className="settings-card">
            <div className="settings-card-head">
              <h4>用户列表</h4>
              <span className="hint">{loading ? '加载中…' : `共 ${users.length} 个账号`}</span>
            </div>
            <div className="settings-card-body accounts-body">
              <div className="accounts-table-wrap">
                <table className="accounts-table">
                  <thead>
                    <tr>
                      <th>用户</th>
                      <th>角色</th>
                      <th>状态</th>
                      <th>最近登录</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && !users.length ? (
                      <tr>
                        <td colSpan={5} className="accounts-empty">
                          加载中…
                        </td>
                      </tr>
                    ) : null}
                    {!loading && !users.length ? (
                      <tr>
                        <td colSpan={5} className="accounts-empty">
                          暂无用户
                        </td>
                      </tr>
                    ) : null}
                    {users.map((u) => {
                      const isSelf = u.id === currentUser.id
                      const rowBusy = busyId === u.id
                      return (
                        <tr key={u.id} className={u.is_active ? undefined : 'is-disabled'}>
                          <td>
                            <div className="accounts-user">
                              <strong>{u.display_name || u.username}</strong>
                              <small>
                                @{u.username}
                                {isSelf ? ' · 当前' : ''}
                              </small>
                            </div>
                          </td>
                          <td>
                            <div className="accounts-roles">
                              {(u.roles || []).map((r) => (
                                <span key={r} className="tag">
                                  {roleLabel(roles, r)}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td>
                            <span className={u.is_active ? 'badge badge-ok' : 'badge badge-down'}>
                              {u.is_active ? '启用' : '禁用'}
                            </span>
                          </td>
                          <td className="accounts-time">{formatTime(u.last_login_at)}</td>
                          <td>
                            <div className="accounts-actions">
                              <button type="button" className="btn ghost sm" disabled={rowBusy} onClick={() => openEdit(u)}>
                                编辑
                              </button>
                              <button
                                type="button"
                                className="btn ghost sm"
                                disabled={rowBusy || isSelf}
                                onClick={() => void onToggleActive(u)}
                              >
                                {u.is_active ? '禁用' : '启用'}
                              </button>
                              <button
                                type="button"
                                className="btn ghost sm danger-text"
                                disabled={rowBusy || isSelf}
                                onClick={() => void onDelete(u)}
                              >
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      {mode ? (
        <div className="modal-backdrop" role="presentation" onClick={closeEditor}>
          <div
            className="modal-card account-editor-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="account-editor-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head account-editor-head">
              <div>
                <h3 id="account-editor-title">{mode === 'create' ? '新增用户' : '编辑用户'}</h3>
                <p className="account-editor-sub">
                  {mode === 'create' ? '创建后台登录账号并分配角色' : `正在编辑 @${editing?.username}`}
                </p>
              </div>
              <button type="button" className="btn ghost sm icon-only" title="关闭" disabled={busyId !== null} onClick={closeEditor}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form className="modal-body account-editor-body" onSubmit={(e) => void onSubmit(e)}>
              <div className={`account-editor-grid ${mode === 'create' ? 'cols-2' : 'cols-1'}`}>
                {mode === 'create' ? (
                  <label className="account-field">
                    <span className="lbl">用户名</span>
                    <input
                      value={form.username}
                      onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                      placeholder="登录名"
                      autoComplete="off"
                      required
                      minLength={2}
                      maxLength={64}
                      autoFocus
                    />
                  </label>
                ) : null}

                <label className="account-field">
                  <span className="lbl">显示名</span>
                  <input
                    value={form.displayName}
                    onChange={(e) => setForm((f) => ({ ...f, displayName: e.target.value }))}
                    placeholder="可选，默认与用户名相同"
                    autoComplete="off"
                    maxLength={64}
                    autoFocus={mode === 'edit'}
                  />
                </label>

                <label className={`account-field ${mode === 'create' ? 'span-2' : ''}`}>
                  <span className="lbl">{mode === 'create' ? '密码' : '新密码'}</span>
                  <input
                    type="password"
                    value={form.password}
                    onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                    placeholder={mode === 'create' ? '至少 6 位' : '留空则不修改'}
                    autoComplete="new-password"
                    required={mode === 'create'}
                    minLength={mode === 'create' ? 6 : undefined}
                  />
                </label>
              </div>

              <div className="account-field">
                <span className="lbl">角色</span>
                <div className="role-chip-row" role="radiogroup" aria-label="角色">
                  {roles.map((r) => {
                    const active = form.role === r.name
                    return (
                      <button
                        key={r.name}
                        type="button"
                        role="radio"
                        className={active ? 'role-chip active' : 'role-chip'}
                        aria-checked={active}
                        onClick={() => selectRole(r.name)}
                      >
                        <strong>{r.label || r.name}</strong>
                        <small>{r.name}</small>
                      </button>
                    )
                  })}
                  {!roles.length ? <p className="hint">暂无角色数据</p> : null}
                </div>
              </div>

              {mode === 'edit' ? (
                <label className={`account-switch ${editing?.id === currentUser.id ? 'is-locked' : ''}`}>
                  <span>
                    <strong>启用账号</strong>
                    <small>{editing?.id === currentUser.id ? '不能禁用当前登录账号' : '关闭后将无法登录'}</small>
                  </span>
                  <input
                    type="checkbox"
                    checked={form.isActive}
                    disabled={editing?.id === currentUser.id}
                    onChange={(e) => setForm((f) => ({ ...f, isActive: e.target.checked }))}
                  />
                </label>
              ) : null}

              {formError ? <p className="hint warn">{formError}</p> : null}

              <div className="account-editor-actions">
                <button type="button" className="btn secondary sm" disabled={busyId !== null} onClick={closeEditor}>
                  取消
                </button>
                <button type="submit" className="btn primary sm" disabled={busyId !== null}>
                  {busyId !== null ? '提交中…' : mode === 'create' ? '创建用户' : '保存更改'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  )
}
