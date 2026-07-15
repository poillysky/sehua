import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import { confirmDialog } from '../ui/confirm'
import { toast } from '../ui/toast'

type Overview = {
  resources: number
  resource_sources: number
  import_jobs: number
  crawl_pages: number
  crawl_pending: number
  crawl_boards: number
  activity_logs: number
}

type DataOverviewResponse = {
  message?: string
  overview: Overview
  crawler_running: boolean
  crawler_enabled: boolean
}

type ResetResult = {
  message?: string
  deleted?: Partial<Overview>
  crawler_enabled?: boolean
}

const STAT_ITEMS: { key: keyof Overview; label: string }[] = [
  { key: 'resources', label: '资源条目' },
  { key: 'resource_sources', label: '资源关联' },
  { key: 'import_jobs', label: '导入任务' },
  { key: 'crawl_pages', label: '爬取页面' },
  { key: 'crawl_pending', label: '待处理队列' },
  { key: 'crawl_boards', label: '板块记录' },
  { key: 'activity_logs', label: '活动日志' },
]

function emptyOverview(): Overview {
  return {
    resources: 0,
    resource_sources: 0,
    import_jobs: 0,
    crawl_pages: 0,
    crawl_pending: 0,
    crawl_boards: 0,
    activity_logs: 0,
  }
}

function fetchDataOverview() {
  return api<DataOverviewResponse>('/api/system/data-overview')
}

function resetAllData(confirmText: string) {
  return api<ResetResult>('/api/system/reset', {
    method: 'POST',
    body: JSON.stringify({ confirm: confirmText }),
  })
}

function formatCount(n: number | undefined) {
  return Number(n || 0).toLocaleString()
}

export function DataMgmtPage() {
  const [confirmText, setConfirmText] = useState('')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [crawlerRunning, setCrawlerRunning] = useState(false)
  const [crawlerEnabled, setCrawlerEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [resetting, setResetting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchDataOverview()
      setOverview(data.overview || emptyOverview())
      setCrawlerRunning(Boolean(data.crawler_running))
      setCrawlerEnabled(Boolean(data.crawler_enabled))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载失败')
      setOverview(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onReset(e: FormEvent) {
    e.preventDefault()
    const text = confirmText.trim()
    if (text !== '清空') {
      toast.warn('请在确认框输入「清空」')
      return
    }
    const ok = await confirmDialog({
      title: '清空数据',
      message: '确定清空所有爬取数据与资源？此操作不可恢复。',
      confirmText: '清空',
      danger: true,
    })
    if (!ok) return

    setResetting(true)
    try {
      const data = await resetAllData(text)
      setConfirmText('')
      setOverview(emptyOverview())
      setCrawlerRunning(false)
      setCrawlerEnabled(false)
      await load()
      toast.success(
        `已删除资源 ${data.deleted?.resources ?? 0} 条、爬取记录 ${data.deleted?.crawl_pages ?? 0} 条`,
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '清空失败')
      await load().catch(() => {})
    } finally {
      setResetting(false)
    }
  }

  const o = overview
  let crawlerHint = ''
  let crawlerHintTone: 'warn' | 'info' = 'info'
  if (crawlerRunning) {
    crawlerHint = '爬虫正在执行中，请先关闭爬虫并等待当前轮次结束后再清空数据。'
    crawlerHintTone = 'warn'
  } else if (crawlerEnabled) {
    crawlerHint = '爬虫开关当前为开启状态，清空时会自动关闭爬虫。'
    crawlerHintTone = 'info'
  }

  return (
    <section className="page page-data active">
      <div className="page-scroll data-mgmt-page">
        <div className="data-mgmt-shell">
          <header className="data-mgmt-intro">
            <div className="data-mgmt-intro-text">
              <h2>数据管理</h2>
              <p>
                清空已爬取的资源、爬虫队列、板块进度与活动日志，使收集器回到初始数据状态。系统设置、论坛配置与账号不会被删除。
              </p>
            </div>
          </header>

          <div className="card data-mgmt-card">
            <div className="data-mgmt-card-head">
              <div>
                <h3>当前数据量</h3>
                <p className="hint">可被重置的库表统计</p>
              </div>
              <button type="button" className="btn ghost sm" onClick={() => void load()} disabled={loading || resetting}>
                {loading ? '刷新中…' : '刷新'}
              </button>
            </div>
            <div className="data-mgmt-card-body">
              <div className="data-overview-grid">
                {STAT_ITEMS.map((item) => {
                  const value = o?.[item.key]
                  const isZero = !loading && Number(value || 0) === 0
                  return (
                    <div key={item.key} className={`data-overview-item${isZero ? ' is-empty' : ''}`}>
                      <span className="lbl">{item.label}</span>
                      <strong>{loading && !o ? '…' : formatCount(value)}</strong>
                    </div>
                  )
                })}
              </div>
              {crawlerHint ? (
                <p className={`data-mgmt-banner data-mgmt-banner--${crawlerHintTone}`}>{crawlerHint}</p>
              ) : null}
            </div>
          </div>

          <div className="card data-mgmt-card data-mgmt-card--danger">
            <div className="data-mgmt-card-head">
              <div>
                <h3>重置所有数据</h3>
                <p className="hint">此操作不可恢复。执行前请先关闭爬虫；若爬虫正在运行，系统将拒绝清空。</p>
              </div>
            </div>
            <div className="data-mgmt-card-body">
              <ul className="data-mgmt-scope">
                <li>所有 ED2K / magnet 资源与标签</li>
                <li>爬虫队列、已处理帖子记录、板块扫描进度</li>
                <li>爬虫活动日志</li>
              </ul>
              <form className="data-reset-form" onSubmit={(e) => void onReset(e)}>
                <label className="data-reset-field">
                  <span className="lbl">输入「清空」以确认</span>
                  <input
                    type="text"
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    placeholder="清空"
                    autoComplete="off"
                    disabled={resetting}
                  />
                </label>
                <div className="data-reset-actions">
                  <button type="submit" className="btn danger" disabled={resetting || confirmText.trim() !== '清空'}>
                    {resetting ? '清空中…' : '清空所有数据'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
