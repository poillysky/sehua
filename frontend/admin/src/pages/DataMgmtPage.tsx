import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import {
  fetchBackupStatus,
  fetchResourceDbConfig,
  importBackupFile,
  runBackupNow,
  saveBackupConfig,
  saveResourceDbConfig,
  testResourceDbConfig,
  type BackupStatus,
  type ResourceDbConfig,
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
  resource_db_separate?: boolean
}

type DataOverviewResponse = {
  message?: string
  overview: Overview
  crawler_running: boolean
  crawler_enabled: boolean
  resource_db?: ResourceDbConfig
  resource_db_error?: string | null
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

function resetCrawlData(confirmText: string) {
  return api<ResetResult>('/api/system/reset-crawl', {
    method: 'POST',
    body: JSON.stringify({ confirm: confirmText }),
  })
}

function resetResourceData(confirmText: string) {
  return api<ResetResult>('/api/system/reset-resources', {
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
  const [confirmCrawl, setConfirmCrawl] = useState('')
  const [confirmResources, setConfirmResources] = useState('')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [crawlerRunning, setCrawlerRunning] = useState(false)
  const [crawlerEnabled, setCrawlerEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [resettingCrawl, setResettingCrawl] = useState(false)
  const [resettingResources, setResettingResources] = useState(false)

  const [backup, setBackup] = useState<BackupStatus | null>(null)
  const [backupEnabled, setBackupEnabled] = useState(false)
  const [backupHour, setBackupHour] = useState(3)
  const [backupMinute, setBackupMinute] = useState(0)
  const [backupLoading, setBackupLoading] = useState(true)
  const [backupSaving, setBackupSaving] = useState(false)
  const [backupRunning, setBackupRunning] = useState(false)
  const [backupImporting, setBackupImporting] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)

  const [rdb, setRdb] = useState<ResourceDbConfig | null>(null)
  const [rdbEnabled, setRdbEnabled] = useState(false)
  const [rdbHost, setRdbHost] = useState('')
  const [rdbPort, setRdbPort] = useState(5432)
  const [rdbUser, setRdbUser] = useState('')
  const [rdbPassword, setRdbPassword] = useState('')
  const [rdbDbname, setRdbDbname] = useState('')
  const [rdbLoading, setRdbLoading] = useState(true)
  const [rdbSaving, setRdbSaving] = useState(false)
  const [rdbTesting, setRdbTesting] = useState(false)

  const applyResourceDb = useCallback((data: ResourceDbConfig) => {
    setRdb(data)
    setRdbEnabled(Boolean(data.enabled))
    setRdbHost(data.host || '')
    setRdbPort(Number(data.port ?? data.primary?.port ?? 5432))
    setRdbUser(data.user || '')
    setRdbDbname(data.dbname || '')
    setRdbPassword('')
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchDataOverview()
      setOverview(data.overview || emptyOverview())
      setCrawlerRunning(Boolean(data.crawler_running))
      setCrawlerEnabled(Boolean(data.crawler_enabled))
      if (data.resource_db) applyResourceDb(data.resource_db)
      if (data.resource_db_error) {
        toast.warn(data.resource_db_error)
      }    } catch (err) {
      toast.error(err instanceof Error ? err.message : '加载失败')
      setOverview(null)
    } finally {
      setLoading(false)
    }
  }, [applyResourceDb])

  const loadResourceDb = useCallback(async () => {
    setRdbLoading(true)
    try {
      const data = await fetchResourceDbConfig()
      applyResourceDb(data)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '读取资源库配置失败')
      setRdb(null)
    } finally {
      setRdbLoading(false)
    }
  }, [applyResourceDb])

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
    void loadResourceDb()
  }, [load, loadBackup, loadResourceDb])

  function resourceDbBody() {
    const password = rdbPassword.trim()
    return {
      enabled: rdbEnabled,
      host: rdbHost.trim(),
      port: Number(rdbPort) || 5432,
      user: rdbUser.trim(),
      dbname: rdbDbname.trim(),
      password: password || null,
      keep_password: !password,
    }
  }

  async function onSaveResourceDb(e: FormEvent) {
    e.preventDefault()
    if (rdbEnabled && (!rdbHost.trim() || !rdbDbname.trim())) {
      toast.warn('启用独立资源库时请填写主机与数据库名')
      return
    }
    setRdbSaving(true)
    try {
      const data = await saveResourceDbConfig(resourceDbBody())
      applyResourceDb(data)
      await load()
      if (data.connection_ok === false) {
        toast.warn(
          data.connection_error ||
            '配置已保存，但独立资源库连不上。跨网络请填对方宿主机/NAS IP + bridge 映射端口。',
        )
      } else {
        toast.success(
          data.using_primary
            ? '已保存 · 资源仍写入主库（与项目源数据同库）'
            : `已保存 · 资源写入 ${data.effective?.host}:${data.effective?.port}/${data.effective?.dbname}`,
        )
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setRdbSaving(false)
    }
  }

  async function onTestResourceDb() {
    setRdbTesting(true)
    try {
      const res = await testResourceDbConfig(resourceDbBody())
      if (res.ok) toast.success(res.message || '连通成功')
      else toast.error(res.message || '连通失败')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '测试失败')
    } finally {
      setRdbTesting(false)
    }
  }

  async function onResetCrawl(e: FormEvent) {
    e.preventDefault()
    const text = confirmCrawl.trim()
    if (text !== '清空爬取') {
      toast.warn('请在确认框输入「清空爬取」')
      return
    }
    const ok = await confirmDialog({
      title: '清空爬取记录',
      message:
        '将删除爬虫队列、已处理/失败/跳过记录、活动日志与列表游标进度；资源库不动。此操作不可恢复。',
      confirmText: '清空爬取',
      danger: true,
    })
    if (!ok) return

    setResettingCrawl(true)
    try {
      const data = await resetCrawlData(text)
      setConfirmCrawl('')
      setCrawlerRunning(false)
      setCrawlerEnabled(false)
      await load()
      toast.success(
        `已清空爬取记录 ${data.deleted?.crawl_pages ?? 0} 条` +
          `（待抓 ${data.deleted?.crawl_pending ?? 0}）`,
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '清空爬取失败')
      await load().catch(() => {})
    } finally {
      setResettingCrawl(false)
    }
  }

  async function onResetResources(e: FormEvent) {
    e.preventDefault()
    const text = confirmResources.trim()
    if (text !== '清空资源') {
      toast.warn('请在确认框输入「清空资源」')
      return
    }
    const ok = await confirmDialog({
      title: '清空资源库',
      message: '将删除全部资源、关联与导入任务；爬取队列与进度保留。此操作不可恢复。',
      confirmText: '清空资源',
      danger: true,
    })
    if (!ok) return

    setResettingResources(true)
    try {
      const data = await resetResourceData(text)
      setConfirmResources('')
      await load()
      toast.success(`已清空资源 ${data.deleted?.resources ?? 0} 条`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '清空资源失败')
      await load().catch(() => {})
    } finally {
      setResettingResources(false)
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

  async function onImportBackup() {
    if (!importFile) {
      toast.warn('请先选择备份文件')
      return
    }
    const ok = await confirmDialog({
      title: '导入备份到资源库',
      message:
        '将把备份中的资源合并进当前库：相同 hash 会更新并去重，不会清空现有数据。若爬虫在跑会先停再导再开。确定？',
      confirmText: '开始导入',
    })
    if (!ok) return
    setBackupImporting(true)
    try {
      const res = await importBackupFile(importFile)
      await load()
      await loadBackup()
      if (res.ok) {
        toast.success(
          `导入完成 · 新增 ${res.resources_inserted} · 更新 ${res.resources_updated}` +
            (res.resources_skipped ? ` · 跳过 ${res.resources_skipped}` : ''),
        )
        setImportFile(null)
      } else {
        toast.error(res.error || '导入失败')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '导入失败')
      await loadBackup().catch(() => {})
    } finally {
      setBackupImporting(false)
    }
  }

  const o = overview
  let crawlerHint = ''
  let crawlerHintTone: 'warn' | 'info' = 'info'
  if (crawlerRunning) {
    crawlerHint = '爬虫正在执行中，请先关闭爬虫并等待当前轮次结束后再清空爬取记录。'
    crawlerHintTone = 'warn'
  } else if (crawlerEnabled) {
    crawlerHint = '爬虫开关当前为开启状态，清空爬取记录时会自动关闭爬虫。'
    crawlerHintTone = 'info'
  }

  const file = backup?.file
  const busy = backupRunning || backupImporting || Boolean(backup?.busy)
  const rdbBusy = rdbSaving || rdbTesting
  const primaryHint = rdb?.primary
    ? `${rdb.primary.host}:${rdb.primary.port}/${rdb.primary.dbname}`
    : '主库（POSTGRES_*）'

  return (
    <section className="page page-data active">
      <div className="page-scroll data-mgmt-page">
        <div className="data-mgmt-shell">
          <header className="data-mgmt-intro">
            <div className="data-mgmt-intro-text">
              <h2>数据管理</h2>
              <p>
                可单独指定资源库连接；爬虫队列、论坛配置与账号仍在主库。备份/导入/清空资源均针对当前资源库；搜索端
                next-web 若拆库需自行指向同一资源库。
              </p>
            </div>
          </header>

          <div className="card data-mgmt-card">
            <div className="data-mgmt-card-head">
              <div>
                <h3>资源数据库</h3>
                <p className="hint">
                  关闭时资源写入主库。开启后资源读写走下方库；不自动建表。跨 Docker / bridge
                  网络请填对方<strong>宿主机或 NAS IP</strong> + <strong>映射端口</strong>
                  （例如 192.168.x.x:5433），不要填本服务 compose 内的主机名 postgres。密码留空则沿用已保存或主库密码。
                </p>
              </div>
            </div>
            <div className="data-mgmt-card-body">
              <form className="data-rdb-form" onSubmit={(e) => void onSaveResourceDb(e)}>
                <label className="data-backup-switch">
                  <input
                    type="checkbox"
                    checked={rdbEnabled}
                    disabled={rdbLoading || rdbBusy || busy}
                    onChange={(e) => {
                      const on = e.target.checked
                      setRdbEnabled(on)
                      if (!on) return
                      const p = rdb?.primary
                      // 跨网络独立库：不自动填本服务内网主机名（如 postgres），避免连错
                      const primaryHost = String(p?.host || '').trim().toLowerCase()
                      const dockerLocal =
                        !primaryHost ||
                        primaryHost === 'postgres' ||
                        primaryHost === 'localhost' ||
                        primaryHost === '127.0.0.1'
                      setRdbHost((h) => {
                        if (h.trim()) return h
                        return dockerLocal ? '' : String(p?.host || '')
                      })
                      setRdbPort((port) => {
                        const n = Number(port)
                        if (n > 0) return n
                        return Number(p?.port ?? 5432) || 5432
                      })
                      setRdbUser((u) => u.trim() || String(p?.user || ''))
                      setRdbDbname((d) => d.trim() || String(p?.dbname || ''))
                    }}
                  />
                  <span>使用独立资源库</span>
                </label>
                <div className={`settings-form-fields${rdbEnabled ? '' : ' is-disabled'}`}>
                  <label>
                    主机
                    <input
                      type="text"
                      value={rdbHost}
                      placeholder="NAS 或宿主机 IP（勿填 postgres）"
                      disabled={!rdbEnabled || rdbLoading || rdbBusy || busy}
                      onChange={(e) => setRdbHost(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    端口
                    <input
                      type="number"
                      min={1}
                      max={65535}
                      value={rdbPort}
                      disabled={!rdbEnabled || rdbLoading || rdbBusy || busy}
                      onChange={(e) => setRdbPort(Math.max(1, Math.min(65535, Number(e.target.value) || 5432)))}
                    />
                  </label>
                  <label>
                    用户
                    <input
                      type="text"
                      value={rdbUser}
                      placeholder={rdb?.primary?.user || 'postgres'}
                      disabled={!rdbEnabled || rdbLoading || rdbBusy || busy}
                      onChange={(e) => setRdbUser(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    数据库名
                    <input
                      type="text"
                      value={rdbDbname}
                      placeholder={rdb?.primary?.dbname || 'ed2k'}
                      disabled={!rdbEnabled || rdbLoading || rdbBusy || busy}
                      onChange={(e) => setRdbDbname(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <label className="settings-field-full">
                    密码{rdb?.has_password ? '（已保存，留空不改）' : ''}
                    <input
                      type="password"
                      value={rdbPassword}
                      placeholder={rdb?.has_password ? '••••••••' : '留空则用主库密码'}
                      disabled={!rdbEnabled || rdbLoading || rdbBusy || busy}
                      onChange={(e) => setRdbPassword(e.target.value)}
                      autoComplete="new-password"
                    />
                  </label>
                </div>
                <p className="hint">
                  当前生效：
                  {rdbLoading
                    ? '…'
                    : rdb?.using_primary
                      ? `主库 ${primaryHint}`
                      : `${rdb?.effective?.host}:${rdb?.effective?.port}/${rdb?.effective?.dbname}`}
                </p>
                <div className="data-backup-actions">
                  <button
                    type="button"
                    className="btn ghost sm"
                    disabled={rdbLoading || rdbBusy || busy}
                    onClick={() => void onTestResourceDb()}
                  >
                    {rdbTesting ? '测试中…' : '测试连接'}
                  </button>
                  <button type="submit" className="btn secondary sm" disabled={rdbLoading || rdbBusy || busy}>
                    {rdbSaving ? '保存中…' : '保存配置'}
                  </button>
                </div>
              </form>
            </div>
          </div>

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
                  void loadResourceDb()
                }}
                disabled={loading || resettingCrawl || resettingResources || busy || rdbBusy}
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

              <div className="data-backup-import">
                <div className="data-backup-import-head">
                  <h4>导入备份</h4>
                  <p className="hint">
                    支持 .sql.gz / .zip。合并进当前库，相同资源 hash 与标签名自动去重，不会整库覆盖。
                  </p>
                </div>
                <div className="data-backup-import-row">
                  <label className={`btn secondary sm import-file-btn${busy ? ' is-disabled' : ''}`}>
                    {importFile ? importFile.name : '选择文件'}
                    <input
                      type="file"
                      accept=".gz,.sql,.zip,application/gzip,application/zip"
                      disabled={backupLoading || busy}
                      hidden
                      onChange={(e) => {
                        const f = e.target.files?.[0] || null
                        setImportFile(f)
                        e.target.value = ''
                      }}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn primary sm"
                    disabled={backupLoading || busy || !importFile}
                    onClick={() => void onImportBackup()}
                  >
                    {backupImporting ? '导入中…' : '导入到数据库'}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="data-reset-grid">
            <div className="card data-mgmt-card data-mgmt-card--danger">
              <div className="data-mgmt-card-head">
                <div>
                  <h3>清空爬取记录</h3>
                  <p className="hint">只清本项目爬虫数据，资源库保留。执行前请先关闭爬虫。</p>
                </div>
              </div>
              <div className="data-mgmt-card-body">
                <ul className="data-mgmt-scope">
                  <li>爬虫队列（待抓 / 异常 / 失败 / 跳过）</li>
                  <li>板块扫描游标与捕新进度</li>
                  <li>爬虫活动日志</li>
                </ul>
                <p className="hint">不会删除资源库、论坛配置、Cookie 与账号。</p>
                <form className="data-reset-form" onSubmit={(e) => void onResetCrawl(e)}>
                  <label className="data-reset-field">
                    <span className="lbl">输入「清空爬取」以确认</span>
                    <input
                      type="text"
                      value={confirmCrawl}
                      onChange={(e) => setConfirmCrawl(e.target.value)}
                      placeholder="清空爬取"
                      autoComplete="off"
                      disabled={resettingCrawl || resettingResources}
                    />
                  </label>
                  <div className="data-reset-actions">
                    <button
                      type="submit"
                      className="btn danger"
                      disabled={
                        resettingCrawl ||
                        resettingResources ||
                        confirmCrawl.trim() !== '清空爬取'
                      }
                    >
                      {resettingCrawl ? '清空中…' : '清空爬取记录'}
                    </button>
                  </div>
                </form>
              </div>
            </div>

            <div className="card data-mgmt-card data-mgmt-card--danger">
              <div className="data-mgmt-card-head">
                <div>
                  <h3>清空资源库</h3>
                  <p className="hint">只清已入库资源，爬取队列与进度保留。</p>
                </div>
              </div>
              <div className="data-mgmt-card-body">
                <ul className="data-mgmt-scope">
                  <li>全部 ED2K / magnet / 占位资源</li>
                  <li>资源关联与标签</li>
                  <li>导入任务记录</li>
                </ul>
                <p className="hint">不会删除爬虫队列、扫描进度与活动日志。</p>
                <form className="data-reset-form" onSubmit={(e) => void onResetResources(e)}>
                  <label className="data-reset-field">
                    <span className="lbl">输入「清空资源」以确认</span>
                    <input
                      type="text"
                      value={confirmResources}
                      onChange={(e) => setConfirmResources(e.target.value)}
                      placeholder="清空资源"
                      autoComplete="off"
                      disabled={resettingCrawl || resettingResources}
                    />
                  </label>
                  <div className="data-reset-actions">
                    <button
                      type="submit"
                      className="btn danger"
                      disabled={
                        resettingCrawl ||
                        resettingResources ||
                        confirmResources.trim() !== '清空资源'
                      }
                    >
                      {resettingResources ? '清空中…' : '清空资源库'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
