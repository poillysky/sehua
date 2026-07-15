import { useEffect, useState } from 'react'
import { useNavigate, useOutletContext, useSearchParams } from 'react-router-dom'
import type { AuthUser } from '../api/auth'
import { fetchSettings, saveSettings } from '../api/settings'
import { SITE_RESOURCE_FORMAT } from '../data/resourceFormat'
import { toast } from '../ui/toast'
import { AccountsPanel } from './AccountsPanel'
import { ForumsPanel } from './ForumsPanel'

type Tab = 'accounts' | 'forums' | 'general'

type ShellContext = {
  user: AuthUser
}

const TABS: Tab[] = ['accounts', 'forums', 'general']

function parseTab(value: string | null): Tab {
  return TABS.includes(value as Tab) ? (value as Tab) : 'accounts'
}

function GeneralSettingsPanel() {
  const [proxy, setProxy] = useState('')
  const [searchFront, setSearchFront] = useState('http://localhost:3008')
  const [intervalLabel, setIntervalLabel] = useState('连续无间隔')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    void fetchSettings()
      .then((s) => {
        setProxy(s.web_crawler_proxy || '')
        setSearchFront(s.search_frontend_url || 'http://localhost:3008')
        setIntervalLabel(s.crawl_interval_label || '连续无间隔')
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : '读取失败'))
      .finally(() => setLoading(false))
  }, [])

  const onSave = async () => {
    setSaving(true)
    try {
      const saved = await saveSettings({
        web_crawler_proxy: proxy.trim(),
        search_frontend_url: searchFront.trim() || 'http://localhost:3008',
      })
      setProxy(saved.web_crawler_proxy || '')
      setSearchFront(saved.search_frontend_url || 'http://localhost:3008')
      toast.success('通用配置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="settings-panel active">
      <header className="settings-panel-head">
        <div>
          <h3>通用配置</h3>
          <p className="settings-panel-desc">站点级参数；爬虫节奏（连续无间隔）与拓扑一致，细参在论坛配置</p>
        </div>
      </header>
      <div className="settings-panel-body">
        <div className="settings-card">
          <div className="settings-card-head">
            <h4>运行参数</h4>
          </div>
          <div className="settings-card-body">
            <div className="settings-form-fields">
              <label>
                爬取间隔
                <input type="text" value={intervalLabel} readOnly disabled />
              </label>
              <label>
                搜索前端
                <input
                  value={searchFront}
                  disabled={loading}
                  onChange={(e) => setSearchFront(e.target.value)}
                />
              </label>
              <label className="settings-field-full">
                HTTP 代理
                <input
                  placeholder="http://127.0.0.1:7890"
                  value={proxy}
                  disabled={loading}
                  onChange={(e) => setProxy(e.target.value)}
                />
              </label>
            </div>
            <p className="hint">代理供联通探测与 HTTP 读帖使用；请求延迟 / 冷却见论坛「爬虫配置」。</p>
            <div className="actions">
              <button type="button" className="btn primary sm" disabled={loading || saving} onClick={() => void onSave()}>
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-card-head">
            <h4>统一入库资源格式</h4>
          </div>
          <div className="settings-card-body">
                    <p className="hint settings-resource-format-desc">
                      全站统一目标字段（论坛爬取 / 人工快速导入 / 解析入库共用）。处理记录左侧「快速导入」弹窗会从
                      <code> GET /api/import/spec </code>
                      加载同一套说明。
                    </p>
            <ol className="resource-format-spec">
              {SITE_RESOURCE_FORMAT.map((field) => (
                <li key={field.no} className="resource-format-item">
                  <span className="resource-format-no">{field.no}</span>
                  <div className="resource-format-body">
                    <strong>{field.name}</strong>
                    {field.note ? <span className="resource-format-note"> · {field.note}</span> : null}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </div>
  )
}

export function SettingsPage() {
  const navigate = useNavigate()
  const { user } = useOutletContext<ShellContext>()
  const [params, setParams] = useSearchParams()
  const tab = parseTab(params.get('tab'))

  const setTab = (next: Tab) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        out.set('tab', next)
        if (next !== 'forums') {
          out.delete('forum')
          out.delete('panel')
        }
        return out
      },
      { replace: true },
    )
  }

  return (
    <section className="page overlay-page active">
      <div className="settings-shell">
        <aside className="settings-sidebar">
          <div className="settings-sidebar-head">
            <div className="settings-brand">
              <span className="settings-brand-icon" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
                </svg>
              </span>
              <div>
                <h2>系统设置</h2>
                <p className="settings-brand-sub">配置收集器运行参数</p>
              </div>
            </div>
            <button type="button" className="btn ghost sm settings-close" title="关闭设置" onClick={() => navigate('/resources')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <nav className="settings-nav">
            <button type="button" className={tab === 'accounts' ? 'settings-nav-item active' : 'settings-nav-item'} onClick={() => setTab('accounts')}>
              <span className="settings-nav-icon" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </span>
              <span className="settings-nav-text">
                <strong>账号管理</strong>
                <small>用户与角色权限</small>
              </span>
            </button>
            <button type="button" className={tab === 'forums' ? 'settings-nav-item active' : 'settings-nav-item'} onClick={() => setTab('forums')}>
              <span className="settings-nav-icon" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M2 12h20M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
                </svg>
              </span>
              <span className="settings-nav-text">
                <strong>论坛管理</strong>
                <small>本站专用 · 独立配置</small>
              </span>
            </button>
            <button type="button" className={tab === 'general' ? 'settings-nav-item active' : 'settings-nav-item'} onClick={() => setTab('general')}>
              <span className="settings-nav-icon" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                </svg>
              </span>
              <span className="settings-nav-text">
                <strong>通用配置</strong>
                <small>代理 · 统一入库格式</small>
              </span>
            </button>
          </nav>
        </aside>

        <main className="settings-main">
          {tab === 'accounts' ? <AccountsPanel currentUser={user} /> : null}

          {tab === 'forums' ? <ForumsPanel /> : null}

          {tab === 'general' ? <GeneralSettingsPanel /> : null}
        </main>
      </div>
    </section>
  )
}
