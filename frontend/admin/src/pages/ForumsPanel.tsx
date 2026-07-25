import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  fetchForumRules,
  saveForumConfig,
  setActiveForum,
  testForumLink,
  type ForumCrawlerConfig,
  type ForumItem,
} from '../api/forums'
import { toast } from '../ui/toast'
import { ForumConfigModal, BasicForumConfigModal, PlannedForumModal, type ForumTab, type BasicForumTab } from './ForumConfigModal'

const FORUM_TABS: ForumTab[] = ['overview', 'boards', 'structure', 'topology', 'config']
const BASIC_FORUM_TABS: BasicForumTab[] = ['overview', 'config']

function parseForumTab(value: string | null): ForumTab {
  return FORUM_TABS.includes(value as ForumTab) ? (value as ForumTab) : 'overview'
}

function parseBasicForumTab(value: string | null): BasicForumTab {
  return BASIC_FORUM_TABS.includes(value as BasicForumTab) ? (value as BasicForumTab) : 'overview'
}

function hasFullCrawlerModule(forum: ForumItem) {
  return !!(forum.crawler_module && forum.crawler_module.trim())
}

type LinkState = 'pending' | 'testing' | 'ok' | 'fail'

type LinkStatus = {
  state: LinkState
  detail: string
}

function ForumTileIcon({ forum }: { forum: ForumItem }) {
  const src = forum.icon_url?.trim()
  if (src) {
    return <img src={src} alt="" className="forum-icon-tile-img" />
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <circle cx="12" cy="12" r="9" />
      <path d="M2 12h20M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
    </svg>
  )
}

function boardCounts(forum: ForumItem) {
  const boards = forum.boards || []
  const uniqueFids = new Set(boards.map((b) => String(b.fid || '').trim()).filter(Boolean))
  const enabledKeys = forum.crawler_config?.enabled_board_fids || []
  return {
    /** 独立 fid 数（真正板块） */
    boards: forum.board_count ?? uniqueFids.size ?? 0,
    /** 爬取单位数（含 fid:typeid 分类） */
    units: forum.unit_count ?? boards.length,
    magnet: boards.filter((b) => b.primary_link === 'magnet').length,
    ed2k: boards.filter((b) => b.primary_link === 'ed2k').length,
    both: boards.filter((b) => b.primary_link === 'both').length,
    enabled: enabledKeys.length,
  }
}

function boardMetaText(forum: ForumItem) {
  const counts = boardCounts(forum)
  if (counts.units <= 0) return '基本配置 · 爬虫模块待接入'
  const boards = counts.boards > 0 ? counts.boards : counts.units
  const magnet = counts.magnet + counts.both
  const ed2k = counts.ed2k + counts.both
  return `${boards} 板块 · 磁力 ${magnet} · ED2K ${ed2k}`
}

function activeNote(forum: ForumItem) {
  if (forum.site_dedicated || forum.id === 'sehuatang') {
    return '调度焦点 · 连续调度将跑色花堂专用爬虫（配置不与其它论坛共用）'
  }
  if (forum.capabilities?.crawlable || hasFullCrawlerModule(forum)) {
    return `调度焦点 · 连续调度将跑该论坛专用爬虫（${forum.crawler_module || forum.id}）`
  }
  if (forum.crawler_registered) {
    return '调度焦点 · 基本配置已接入；爬虫能力位未就绪时调度不会抓取'
  }
  return '调度焦点 · 该论坛尚无专用爬虫，连续调度会跳过'
}

function forumBadge(forum: ForumItem, focused: boolean) {
  const registered = !!(forum.crawler_registered || forum.capabilities?.registered)
  if (!registered) {
    return <span className="tag tag-pending">待接入</span>
  }
  // 色花堂 / 2048 / 其它已接入论坛：同一套状态文案与样式
  if (focused) {
    return <span className="tag tag-active">调度焦点</span>
  }
  const full = !!(forum.capabilities?.crawlable || hasFullCrawlerModule(forum))
  return <span className="tag tag-done">{full ? '已接入' : '配置已接入'}</span>
}

function linkStatusText(state: LinkState) {
  if (state === 'ok') return '链接正常'
  if (state === 'fail') return '链接失败'
  return '检测中...'
}

export function ForumsPanel() {
  const [params, setParams] = useSearchParams()
  const openId = params.get('forum')
  const modalTab = parseForumTab(params.get('panel'))
  const basicModalTab = parseBasicForumTab(params.get('panel'))
  const [forums, setForums] = useState<ForumItem[]>([])
  const [activeForumId, setActiveForumId] = useState('sehuatang')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [linkStatus, setLinkStatus] = useState<Record<string, LinkStatus>>({})
  const probeGen = useRef<Record<string, number>>({})

  const setOpenId = (forumId: string | null) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        out.set('tab', 'forums')
        if (forumId) {
          out.set('forum', forumId)
          const panel = out.get('panel')
          if (!panel || (!FORUM_TABS.includes(panel as ForumTab) && !BASIC_FORUM_TABS.includes(panel as BasicForumTab))) {
            out.set('panel', 'overview')
          }
        } else {
          out.delete('forum')
          out.delete('panel')
        }
        return out
      },
      { replace: true },
    )
  }

  const setModalTab = (panel: ForumTab) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        out.set('tab', 'forums')
        if (openId) out.set('forum', openId)
        out.set('panel', panel)
        return out
      },
      { replace: true },
    )
  }

  const setBasicModalTab = (panel: BasicForumTab) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        out.set('tab', 'forums')
        if (openId) out.set('forum', openId)
        out.set('panel', panel)
        return out
      },
      { replace: true },
    )
  }

  const probeLink = useCallback(async (forumId: string) => {
    const gen = (probeGen.current[forumId] || 0) + 1
    probeGen.current[forumId] = gen
    setLinkStatus((prev) => ({
      ...prev,
      [forumId]: { state: 'testing', detail: '正在检测论坛链接…' },
    }))
    try {
      const data = await testForumLink(forumId)
      if (probeGen.current[forumId] !== gen) return
      const host =
        (data.final_url || data.test_url || '')
          .replace(/^https?:\/\//i, '')
          .split('/')[0] || ''
      setLinkStatus((prev) => ({
        ...prev,
        [forumId]: {
          state: data.ok ? 'ok' : 'fail',
          detail: data.ok
            ? [
                data.elapsed_ms != null ? `${data.elapsed_ms}ms` : null,
                data.status_code != null ? `HTTP ${data.status_code}` : null,
                host || null,
              ]
                .filter(Boolean)
                .join(' · ')
            : data.message || data.test_url || '',
        },
      }))    } catch (err) {
      if (probeGen.current[forumId] !== gen) return
      setLinkStatus((prev) => ({
        ...prev,
        [forumId]: {
          state: 'fail',
          detail: err instanceof Error ? err.message : '检测失败',
        },
      }))
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchForumRules()
      const list = data.forums || []
      setForums(list)
      setActiveForumId(data.focus_forum_id || data.active_forum_id || data.site_crawler_forum_id || 'sehuatang')
      const active = list.filter(
        (f) => f.status === 'active' && (f.crawler_registered || f.capabilities?.crawlable),
      )
      for (const forum of active) {
        void probeLink(forum.id)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '论坛配置加载失败')
      setForums([])
    } finally {
      setLoading(false)
    }
  }, [probeLink])

  useEffect(() => {
    void load()
  }, [load])

  const activeForum = forums.find((f) => f.id === activeForumId)
  const openForum = openId ? forums.find((f) => f.id === openId) || null : null

  const handleEnable = async (forumId: string) => {
    if (busy || forumId === activeForumId) return
    const target = forums.find((f) => f.id === forumId)
    if (!target?.crawler_registered && !target?.capabilities?.crawlable) {
      toast.warn('该论坛尚未接入，不能设为调度焦点')
      return
    }
    setBusy(true)
    try {
      const res = await setActiveForum(forumId)
      setActiveForumId(res.active_forum_id || res.focus_forum_id || forumId)
      toast.success(`已设为调度焦点：${target?.name || forumId}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '切换调度焦点失败')
    } finally {
      setBusy(false)
    }
  }

  const handleSaveConfig = async (config: ForumCrawlerConfig) => {
    if (!openForum?.crawler_registered || !openForum.crawler_config) {
      throw new Error('仅已接入的专用爬虫可保存配置')
    }
    const res = await saveForumConfig(openForum.id, config)
    setForums((prev) =>
      prev.map((f) => (f.id === openForum.id ? { ...f, crawler_config: res.config } : f)),
    )
  }

  const handleActiveBoardChange = (config: ForumCrawlerConfig) => {
    if (!openId) return
    setForums((prev) => prev.map((f) => (f.id === openId ? { ...f, crawler_config: config } : f)))
  }

  const openForumConfig = (forum: ForumItem) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        out.set('tab', 'forums')
        out.set('forum', forum.id)
        out.set('panel', 'overview')
        return out
      },
      { replace: true },
    )
  }

  return (
    <div className="settings-panel active">
      <header className="settings-panel-head">
        <div>
          <h3>论坛管理</h3>
          <p className="settings-panel-desc">
            各论坛独立爬虫与配置；入口、板块与 Cookie 互不共用。选中焦点后，连续调度只跑该论坛。
          </p>
        </div>
      </header>

      <div className="settings-panel-body">
        <div className="settings-card">
          <div className="settings-card-head">
            <h4>调度焦点</h4>
          </div>
          <div className="settings-card-body">
            <div className="forum-active-summary">
              {activeForum ? (
                <>
                  <span className="tag tag-active">{activeForum.name}</span>
                  <span className="forum-active-note">{activeNote(activeForum)}</span>
                </>
              ) : (
                <span className="hint">未选择调度焦点</span>
              )}
            </div>

            {loading ? <p className="hint">加载中…</p> : null}

            {!loading ? (
              <div className="forum-icon-grid">
                {forums.map((forum) => {
                  const available =
                    forum.status === 'active' &&
                    !!(forum.crawler_registered || forum.capabilities?.crawlable)
                  const enabled = activeForumId === forum.id
                  const fullModule = !!(forum.capabilities?.crawlable || hasFullCrawlerModule(forum))
                  const status = linkStatus[forum.id] || { state: 'pending' as const, detail: '' }
                  return (
                    <div
                      key={forum.id}
                      className={`forum-icon-wrap${enabled ? ' forum-icon-wrap-enabled' : ''}${available ? '' : ' forum-icon-wrap-planned'}`}
                    >
                      <div className="forum-icon-toolbar">
                        <label
                          className="forum-enable-radio"
                          title={available ? '设为连续调度焦点（各论坛配置仍独立）' : '需接入后才可设为焦点'}
                        >
                          <input
                            type="radio"
                            name="active_forum_id"
                            value={forum.id}
                            checked={enabled}
                            disabled={!available || busy}
                            onChange={() => void handleEnable(forum.id)}
                          />
                          <span className="forum-enable-dot" aria-hidden />
                          <span>焦点</span>
                        </label>
                        {available ? (
                          <button
                            type="button"
                            className={`forum-link-status forum-link-status-${status.state}`}
                            title={status.detail || '点击重新检测论坛链接'}
                            onClick={() => void probeLink(forum.id)}
                          >
                            {linkStatusText(status.state)}
                          </button>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        className={`forum-icon-tile${available ? '' : ' forum-icon-tile-planned'}`}
                        onClick={() => openForumConfig(forum)}
                        title={available ? `打开 ${forum.name} 配置` : `查看 ${forum.name}（待接入）`}
                      >
                        <span className="forum-icon-tile-icon" aria-hidden>
                          <ForumTileIcon forum={forum} />
                        </span>
                        <span className="forum-icon-tile-name">{forum.name}</span>
                        <span className="forum-icon-tile-meta">
                          {available
                            ? fullModule
                              ? boardMetaText(forum)
                              : '基本配置 · 爬虫模块待接入'
                            : '配置不通用 · 需独立模块'}
                        </span>
                        {forumBadge(forum, enabled)}
                      </button>
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {openForum &&
      openForum.status === 'active' &&
      openForum.crawler_registered &&
      openForum.crawler_config &&
      hasFullCrawlerModule(openForum) ? (
        <ForumConfigModal
          forum={openForum as ForumItem & { crawler_config: ForumCrawlerConfig }}
          activeForumId={activeForumId}
          tab={modalTab}
          onTabChange={setModalTab}
          onClose={() => setOpenId(null)}
          onSaveConfig={handleSaveConfig}
          onActiveBoardChange={handleActiveBoardChange}
        />
      ) : null}

      {openForum &&
      openForum.status === 'active' &&
      openForum.crawler_registered &&
      openForum.crawler_config &&
      !hasFullCrawlerModule(openForum) ? (
        <BasicForumConfigModal
          forum={openForum as ForumItem & { crawler_config: ForumCrawlerConfig }}
          activeForumId={activeForumId}
          tab={basicModalTab}
          onTabChange={setBasicModalTab}
          onClose={() => setOpenId(null)}
          onSaveConfig={handleSaveConfig}
        />
      ) : null}

      {openForum && (openForum.status !== 'active' || !openForum.crawler_registered) ? (
        <PlannedForumModal forum={openForum} onClose={() => setOpenId(null)} />
      ) : null}
    </div>
  )
}
