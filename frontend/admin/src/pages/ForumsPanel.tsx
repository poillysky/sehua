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
import { ForumConfigModal, type ForumTab } from './ForumConfigModal'

const FORUM_TABS: ForumTab[] = ['overview', 'boards', 'structure', 'topology', 'config']

function parseForumTab(value: string | null): ForumTab {
  return FORUM_TABS.includes(value as ForumTab) ? (value as ForumTab) : 'overview'
}

type LinkState = 'pending' | 'testing' | 'ok' | 'fail'

type LinkStatus = {
  state: LinkState
  detail: string
}

function ForumTileIcon({ forumId }: { forumId: string }) {
  if (forumId === 'sehuatang') {
    return <img src="/sehuatang-forum-icon.png" alt="" className="forum-icon-tile-img" />
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
  return {
    total: forum.board_count ?? boards.length,
    magnet: boards.filter((b) => b.primary_link === 'magnet').length,
    ed2k: boards.filter((b) => b.primary_link === 'ed2k').length,
  }
}

function activeNote(forum: ForumItem) {
  if (forum.site_dedicated || forum.id === 'sehuatang') {
    return '当前启用 · 调度器将运行色花堂专用爬虫（本站；配置不与其它论坛共用）'
  }
  if (forum.crawler_registered) {
    return `当前启用 · 调度器将运行该论坛的专用爬虫程序${forum.crawler_module ? `（${forum.crawler_module}）` : ''}`
  }
  return '当前启用 · 该论坛尚无专用爬虫，爬取任务会被跳过'
}

function forumBadge(forum: ForumItem, enabled: boolean) {
  if (forum.site_dedicated || forum.id === 'sehuatang') {
    return enabled ? (
      <span className="tag tag-active">本站专用 · 当前启用</span>
    ) : (
      <span className="tag tag-done">本站专用爬虫</span>
    )
  }
  if (!forum.crawler_registered) {
    return <span className="tag tag-pending">待独立接入</span>
  }
  return enabled ? <span className="tag tag-active">当前启用</span> : <span className="tag tag-done">专用爬虫已接入</span>
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
  const [forums, setForums] = useState<ForumItem[]>([])
  const [activeForumId, setActiveForumId] = useState('sehuatang')
  const [siteCrawlerId, setSiteCrawlerId] = useState('sehuatang')
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
          if (!out.get('panel') || !FORUM_TABS.includes(out.get('panel') as ForumTab)) {
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
      setLinkStatus((prev) => ({
        ...prev,
        [forumId]: {
          state: data.ok ? 'ok' : 'fail',
          detail:
            data.elapsed_ms != null
              ? `${data.elapsed_ms}ms · HTTP ${data.status_code ?? '-'}`
              : data.message || data.test_url || '',
        },
      }))
    } catch (err) {
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
      setActiveForumId(data.active_forum_id || data.site_crawler_forum_id || 'sehuatang')
      setSiteCrawlerId(data.site_crawler_forum_id || 'sehuatang')
      const active = list.filter((f) => f.status === 'active' && f.crawler_registered)
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
  const openForum =
    openId && forums.find((f) => f.id === openId)?.crawler_config
      ? (forums.find((f) => f.id === openId) as ForumItem & { crawler_config: ForumCrawlerConfig })
      : null

  const handleEnable = async (forumId: string) => {
    if (busy || forumId === activeForumId) return
    const target = forums.find((f) => f.id === forumId)
    if (!target?.crawler_registered) {
      toast.warn('该论坛尚无专用爬虫，不能启用；接入独立模块后再选')
      return
    }
    setBusy(true)
    try {
      const res = await setActiveForum(forumId)
      setActiveForumId(res.active_forum_id)
      toast.success(`已启用专用爬虫：${target.name}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '切换启用论坛失败')
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
    if (!forum.crawler_registered) {
      toast.warn('其他论坛需独立爬虫模块与独立配置，不能打开色花堂配置页')
      return
    }
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
            色花堂为本站专用爬虫；后续论坛各自独立模块与配置，互不共用
          </p>
        </div>
      </header>

      <div className="settings-panel-body">
        <div className="settings-card">
          <div className="settings-card-head">
            <h4>当前爬虫</h4>
          </div>
          <div className="settings-card-body">
            <div className="forum-active-summary">
              {activeForum ? (
                <>
                  <span className="tag tag-active">{activeForum.name}</span>
                  <span className="forum-active-note">{activeNote(activeForum)}</span>
                </>
              ) : (
                <span className="hint">未选择启用论坛</span>
              )}
            </div>

            {loading ? <p className="hint">加载中…</p> : null}

            {!loading ? (
              <div className="forum-icon-grid">
                {forums.map((forum) => {
                  const dedicated = !!(forum.site_dedicated || forum.id === siteCrawlerId)
                  const available = forum.status === 'active' && !!forum.crawler_registered
                  const enabled = activeForumId === forum.id
                  const counts = boardCounts(forum)
                  const status = linkStatus[forum.id] || { state: 'pending' as const, detail: '' }
                  return (
                    <div
                      key={forum.id}
                      className={`forum-icon-wrap${enabled ? ' forum-icon-wrap-enabled' : ''}${available ? '' : ' forum-icon-wrap-planned'}${dedicated ? ' forum-icon-wrap-site' : ''}`}
                    >
                      <div className="forum-icon-toolbar">
                        <label
                          className="forum-enable-radio"
                          title={available ? '设为当前专用爬虫' : '需独立爬虫接入后才可启用'}
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
                          <span>启用</span>
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
                        className={`forum-icon-tile${dedicated ? ' forum-icon-tile-site' : ''}`}
                        disabled={!available}
                        onClick={() => openForumConfig(forum)}
                        title={
                          available
                            ? '打开色花堂专用配置'
                            : '待独立接入：配置与色花堂不通用'
                        }
                      >
                        <span className="forum-icon-tile-icon" aria-hidden>
                          <ForumTileIcon forumId={forum.id} />
                        </span>
                        <span className="forum-icon-tile-name">{forum.name}</span>
                        {available ? (
                          <span className="forum-icon-tile-meta">
                            {counts.total} 板块 · 磁力 {counts.magnet} · ED2K {counts.ed2k}
                          </span>
                        ) : (
                          <span className="forum-icon-tile-meta">配置不通用 · 需独立模块</span>
                        )}
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

      {openForum ? (
        <ForumConfigModal
          forum={openForum}
          activeForumId={activeForumId}
          tab={modalTab}
          onTabChange={setModalTab}
          onClose={() => setOpenId(null)}
          onSaveConfig={handleSaveConfig}
          onActiveBoardChange={handleActiveBoardChange}
        />
      ) : null}
    </div>
  )
}
