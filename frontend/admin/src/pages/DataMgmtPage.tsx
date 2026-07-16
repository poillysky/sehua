import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import {
  fetchBackupStatus,
  runBackupNow,
  saveBackupConfig,
  type BackupStatus,
} from '../api/system'
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
  { key: 'crawl_pages', label: '爬取页面' },
  { key: 'crawl_pending', label: '待处理队列' },
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

function formatBytes(n: number | undefined) {
  const v = Number(n || 0)
  if (v < 1024) return `${v} B`
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`
  return `${(v / (1024 * 1024)).toFixed(2)} MB`
}

export function DataMgmtPage() {
  const [confirmText, setConfirmText] = useState('')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [crawlerRunning, setCrawlerRunning] = useState(false)
  const [crawlerEnabled, setCrawlerEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [resetting, setResetting] = useState(false)

  const [backup, setBackup] = useState<BackupStatus | null>(null)
  const [backupEnabled, setBackupEnabled] = useState(false)
  const [backupHour, setBackupHour] = useState(3)
  const [backupMinute, setBackupMinute] = useState(0)
  const [backupLoading, setBackupLoading] = useState(true)
  const [backupSaving, setBackupSaving] = useState(false)
  const [backupRunning, setBackupRunning] = useState(false)

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

  const loadBackup = useCallback(async () => {
    setBackupLoading(true)
    try {
      const data = await fetchBackupStatus()
      setBackup(data)
      setBackupEnabled(Boolean(data.enabled))
      setBackupHour(Number(data.hour ?? 3))
      setBackupMinute(Number(data.minute ?? 0))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '读取备份配置失败')
      setBackup(null)
    } finally {
      setBackupLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
    void loadBackup()
  }, [load, loadBackup])

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

  async function onSaveBackup(e: FormEvent) {
    e.preventDefault()
    setBackupSaving(true)
    try {
      const data = await saveBackupConfig({
        enabled: backupEnabled,
        hour: backupHour,
        minute: backupMinute,
      })
      setBackup(data)
      toast.success('备份配置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setBackupSaving(false)
    }
  }

  async function onRunBackup() {
    const ok = await confirmDialog({
      title: '立即备份资源库',
      message:
        '将覆盖磁盘上的同一份资源备份。若爬虫正在运行，会先停止，备份完成后再按原状态恢复。确定？',
      confirmText: '开始备份',
    })
    if (!ok) return
    setBackupRunning(true)
    try {
      const res = await runBackupNow()
      await loadBackup()
      await load()
      if (res.ok) {
        toast.success(`备份成功 · ${formatBytes(res.bytes ?? res.file?.bytes)}`)
      } else {
        toast.error(res.error || '备份失败')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '备份失败')
      await loadBackup().catch(() => {})
    } finally {
      setBackupRunning(false)
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

  const file = backup?.file
  const busy = backupRunning || Boolean(backup?.busy)

  return (
    <section className="page page-data active">
      <div className="page-scroll data-mgmt-page">
        <div className="data-mgmt-shell">
          <header className="data-mgmt-intro">
            <div className="data-mgmt-intro-text">
              <h2>数据管理</h2>
              <p>
                管理资源库备份与数据重置。备份只保留一份完整资源快照；清空不会删除系统设置、论坛配置与账号。
              </p>
            </div>
          </header>

          <div className="card data-mgmt-card">
            <div className="data-mgmt-card-head">
              <div>
                <h3>当前数据量</h3>
                <p className="hint">可被重置的库表统计</p>
              </div>
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  void load()
                  void loadBackup()
                }}
                disabled={loading || resetting || busy}
              >
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

          <div className="card data-mgmt-card">
            <div className="data-mgmt-card-head">
              <div>
                <h3>资源库备份</h3>
                <p className="hint">
                  每日覆盖同一份完整资源备份（不含爬虫队列）。执行时若爬虫在跑会先停再备再开。
                </p>
              </div>
            </div>
            <div className="data-mgmt-card-body">
              <form className="data-backup-form" onSubmit={(e) => void onSaveBackup(e)}>
                <label className="data-backup-switch">
                  <input
                    type="checkbox"
                    checked={backupEnabled}
                    disabled={backupLoading || backupSaving || busy}
                    onChange={(e) => setBackupEnabled(e.target.checked)}
                  />
                  <span>每日自动备份</span>
                </label>
                <div className="data-backup-time">
                  <label>
                    <span className="lbl">时</span>
                    <input
                      type="number"
                      min={0}
                      max={23}
                      value={backupHour}
                      disabled={backupLoading || backupSaving || busy}
                      onChange={(e) => setBackupHour(Math.max(0, Math.min(23, Number(e.target.value) || 0)))}
                    />
                  </label>
                  <label>
                    <span className="lbl">分</span>
                    <input
                      type="number"
                      min={0}
                      max={59}
                      value={backupMinute}
                      disabled={backupLoading || backupSaving || busy}
                      onChange={(e) =>
                        setBackupMinute(Math.max(0, Math.min(59, Number(e.target.value) || 0)))
                      }
                    />
                  </label>
                </div>
                <div className="data-backup-actions">
                  <button type="submit" className="btn secondary sm" disabled={backupLoading || backupSaving || busy}>
                    {backupSaving ? '保存中…' : '保存配置'}
                  </button>
                  <button
                    type="button"
                    className="btn primary sm"
                    disabled={backupLoading || busy}
                    onClick={() => void onRunBackup()}
                  >
                    {busy ? '备份中…' : '立即备份'}
                  </button>
                </div>
              </form>
              <div className="data-backup-status">
                {backupLoading && !backup ? (
                  <p className="hint">读取备份状态…</p>
                ) : (
                  <>
                    <p>
                      当前文件：
                      {file?.exists
                        ? `${file.filename || 'ed2k-resources.sql.gz'} · ${formatBytes(file.bytes)}`
                        : '尚未生成'}
                      {file?.mtime ? ` · ${file.mtime}` : ''}
                    </p>
                    <p>
                      上次结果：
                      {backup?.last_at
                        ? `${backup.last_ok ? '成功' : '失败'} · ${backup.last_at}`
                        : '无'}
                      {backup?.last_ok && backup.last_bytes
                        ? ` · ${formatBytes(backup.last_bytes)}`
                        : ''}
                      {!backup?.last_ok && backup?.last_error ? ` · ${backup.last_error}` : ''}
                    </p>
                  </>
                )}
              </div>
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
