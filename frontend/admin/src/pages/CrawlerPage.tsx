import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchCrawlerStatus,
  fetchDiscardedTids,
  fetchQueueBrowse,
  recrawlAccountStubs,
  requeueDiscardedTids,
  retryAbnormalQueue,
  runCrawlerOnce,
  scanHeadOnce,
  setCrawlerEnabled,
  startCrawlerLoop,
  startRandomTidLoop,
  stopCrawler,
  type CrawlerStatus,
  type QueueBrowseItem,
  type QueueBrowseKind,
} from '../api/crawler'
import { confirmDialog } from '../ui/confirm'
import { toast } from '../ui/toast'

const DISCARDED_PAGE = 30

const STATUS_LABEL: Record<string, string> = {
  failed: '失败丢弃',
  skipped: '跳过',
  pending: '待抓',
  stub: '占位',
}

const QUEUE_MODAL_META: Record<
  QueueBrowseKind,
  { title: string; sub: string; reasonLabel: string }
> = {
  abnormal: {
    title: '异常帖明细',
    sub: '失败/重试贴（含软文拦截壳）。可点「异常重试」在本队列重爬',
    reasonLabel: '错误',
  },
  ready: {
    title: '正常队列明细',
    sub: '启用子板尚未失败的待抓帖',
    reasonLabel: '备注',
  },
  discarded: {
    title: '未正常处理明细',
    sub: '失败丢弃 / 跳过。「失败」与「无阅读权限跳过」请用「账号重爬」处理',
    reasonLabel: '原因',
  },
  stubs: {
    title: '优先占位明细',
    sub: '需登录 / 无阅读权限 / 无权限下载附件。点「账号重爬」用账号 Cookie 处理',
    reasonLabel: '占位原因',
  },
}

function formatWhen(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso.slice(0, 19).replace('T', ' ')
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function discardedReason(row: QueueBrowseItem): string {
  return (
    row.import_outcome ||
    row.outcome ||
    row.last_error ||
    '—'
  ).trim() || '—'
}

function rowUrl(row: QueueBrowseItem): string {
  return (row.url || row.source_url || '').trim()
}

function rowTitle(row: QueueBrowseItem): string {
  return (row.thread_title || row.title || '').trim() || '—'
}

function rowTid(row: QueueBrowseItem): number | null {
  const raw = row.tid
  if (raw == null) return null
  const n = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(n) && n > 0 ? n : null
}

function rowStatus(row: QueueBrowseItem, kind: QueueBrowseKind): string {
  if (kind === 'stubs') return 'stub'
  if (kind === 'ready' || kind === 'abnormal') return 'pending'
  return row.status || '—'
}

function activityLevelClass(msg: string): string {
  const m = msg || ''
  // 「失败 0」只是汇总计数，不当错误
  const failCount = m.match(/失败\s*(\d+)/)
  const zeroFail = failCount ? Number(failCount[1]) === 0 : false
  // 跳过：琥珀（具体原因在文案里）
  if (
    (m.includes('跳过') || m.includes('随机跳过')) &&
    !m.includes('跳过已入库') &&
    !m.includes('列表所见均已入库')
  ) {
    return 'activity-skip'
  }
  // 成功：绿（优先于「异常队列」等词）
  if (
    m.includes('本轮结束') ||
    m.includes('已启动') ||
    m.includes('已开启') ||
    m.includes('进站就绪') ||
    m.includes('正常入库') ||
    m.includes('占位入库') ||
    m.includes('随机入库') ||
    m.includes('已入库重爬结束') ||
    m.includes('已入库批量重爬结束') ||
    (m.includes('已入库批量重爬') && zeroFail) ||
    m.includes('扫新帖完成') ||
    m.includes('改板块') ||
    m.includes('随机抓帖结束') ||
    m.includes('随机抓帖本轮结束') ||
    m.includes('随机抓帖连续调度已启动') ||
    m.includes('本批入库已达上限') ||
    m.includes('账号爬占位结束') ||
    m.includes('账号爬占位升级') ||
    m.includes('账号爬未处理') ||
    m.includes('未处理重入队') ||
    m.includes('未处理批量重入队') ||
    m.includes('未处理批量重爬') ||
    m.includes('未处理重爬') ||
    /重试结束/.test(m) ||
    /完成[：:]/.test(m)
  ) {
    return 'activity-success'
  }
  // 报错：红
  if (
    m.includes('熔断') ||
    m.includes('本轮异常') ||
    m.includes('已入库重爬失败') ||
    (m.includes('抓帖') && m.includes('失败')) ||
    m.includes('随机失败') ||
    m.includes('停板') ||
    m.includes('错误') ||
    (m.includes('失败') && !zeroFail && !m.includes('成功才出队'))
  ) {
    return 'activity-error'
  }
  // 普通信息：白
  return 'activity-info'
}

/** 从爬虫配置解析帖页根地址 */
function forumThreadRoot(webCrawlUrls?: string | null): string {
  const first = (webCrawlUrls || '')
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .find(Boolean)
  if (!first) return 'https://www.sehuatang.net/'
  try {
    const u = new URL(first.includes('://') ? first : `https://${first}`)
    return `${u.protocol}//${u.host}/`
  } catch {
    return 'https://www.sehuatang.net/'
  }
}

function threadPageUrl(tid: string, webCrawlUrls?: string | null): string {
  return `${forumThreadRoot(webCrawlUrls)}thread-${tid}-1-1.html`
}

/** 活动日志：把 tid=123 渲染成可点击外链 */
function ActivityMsg({ msg, webCrawlUrls }: { msg: string; webCrawlUrls?: string | null }) {
  const text = msg || ''
  const parts: Array<string | { tid: string }> = []
  const re = /tid=(\d+)/gi
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    parts.push({ tid: m[1] })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  if (!parts.length) return <>{text}</>
  return (
    <>
      {parts.map((p, i) =>
        typeof p === 'string' ? (
          <span key={i}>{p}</span>
        ) : (
          <a
            key={`${p.tid}-${i}`}
            className="activity-tid-link"
            href={threadPageUrl(p.tid, webCrawlUrls)}
            target="_blank"
            rel="noopener noreferrer"
            title={`打开帖子 tid=${p.tid}`}
            onClick={(e) => e.stopPropagation()}
          >
            tid={p.tid}
          </a>
        ),
      )}
    </>
  )
}

function formatResultLine(status: CrawlerStatus | null, runHint: string): string {
  if (runHint) return runHint
  if (!status) return ''
  const last = status.last_result
  if (!last || typeof last !== 'object') return ''
  if (last.skipped) return `跳过：${String(last.reason || '本轮未执行')}`
  if (last.reason === 'stopped') {
    return `已停止：处理 ${last.crawled ?? 0} · 入库 ${last.imports ?? 0} · 队列已保留`
  }
  if (last.ok === false) return `失败：${String(last.error || last.reason || '本轮失败')}`
  if (last.mode === 'random_tid') {
    return (
      `随机一轮：探测 ${last.probed ?? 0}` +
      ` · 入库 ${last.imported ?? 0}` +
      ` · 占位 ${last.stubbed ?? 0}` +
      ` · 缺失 ${last.missing ?? 0}` +
      ` · 重复 ${last.skipped_dup ?? 0}`
    )
  }
  if (status.last_finished_at || last.crawled != null) {
    const upd = Number(last.board_updated ?? 0)
    return (
      `完成：新帖 ${last.enqueued ?? last.discovered ?? 0}` +
      (upd > 0 ? ` · 改板块 ${upd}` : '') +
      ` · 处理 ${last.crawled ?? 0} · 入库 ${last.imports ?? 0}`
    )
  }
  return ''
}

function formatStubHint(p: {
  active: boolean
  done: number
  remaining: number
  upgraded: number
  still: number
  failed: number
}): string {
  if (p.active) {
    return (
      `账号重爬进行中：已处理 ${p.done} · 库内剩余 ${p.remaining}` +
      ` · 升级 ${p.upgraded} · 仍占位 ${p.still} · 失败 ${p.failed}`
    )
  }
  return (
    `账号重爬结束：处理 ${p.done} · 升级 ${p.upgraded}` +
    ` · 仍占位 ${p.still} · 失败 ${p.failed} · 库内剩余 ${p.remaining}`
  )
}

export function CrawlerPage() {
  const [status, setStatus] = useState<CrawlerStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [runHint, setRunHint] = useState('')
  const autoLoopTried = useRef(false)
  const stubWasActive = useRef(false)

  const [discStatus, setDiscStatus] = useState<'all' | 'failed' | 'skipped'>('failed')
  const [discQInput, setDiscQInput] = useState('')
  const [discQ, setDiscQ] = useState('')
  const [discReason, setDiscReason] = useState('')
  const [discReasons, setDiscReasons] = useState<Array<{ reason: string; count: number }>>([])
  const [discOffset, setDiscOffset] = useState(0)
  const [discItems, setDiscItems] = useState<QueueBrowseItem[]>([])
  const [discTotal, setDiscTotal] = useState(0)
  const [discCounts, setDiscCounts] = useState({ failed: 0, skipped: 0, total: 0 })
  const [discKindCounts, setDiscKindCounts] = useState<Record<string, number>>({})
  const [discLoading, setDiscLoading] = useState(false)
  const [queueModal, setQueueModal] = useState<QueueBrowseKind | null>(null)
  const [discSelected, setDiscSelected] = useState<Set<number>>(() => new Set())
  const [discRequeueBusy, setDiscRequeueBusy] = useState(false)
  const [discRequeueNote, setDiscRequeueNote] = useState('')
  const [discSelectAllBusy, setDiscSelectAllBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const next = await fetchCrawlerStatus()
      setStatus(next)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '读取爬虫状态失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDiscarded = useCallback(async () => {
    if (!queueModal) return
    setDiscLoading(true)
    try {
      const res = await fetchQueueBrowse({
        kind: queueModal,
        status: queueModal === 'discarded' ? discStatus : undefined,
        q: discQ,
        reason: discReason || undefined,
        limit: DISCARDED_PAGE,
        offset: discOffset,
      })
      setDiscItems(res.items || [])
      setDiscTotal(Number(res.total || 0))
      setDiscReasons(res.reasons || [])
      if (res.counts) {
        setDiscCounts({
          failed: Number(res.counts.failed || 0),
          skipped: Number(res.counts.skipped || 0),
          total: Number(res.counts.total || 0),
        })
      }
      if (res.kind_counts) setDiscKindCounts(res.kind_counts)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '读取明细失败')
    } finally {
      setDiscLoading(false)
    }
  }, [queueModal, discStatus, discQ, discReason, discOffset])

  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === 'hidden') return
      void refresh()
    }
    tick()
    const timer = window.setInterval(tick, 5000)
    const onVis = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [refresh])

  useEffect(() => {
    if (!queueModal) return
    void loadDiscarded()
  }, [queueModal, loadDiscarded])

  useEffect(() => {
    if (!queueModal) return
    const body = document.body
    body.classList.add('modal-open')
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setQueueModal(null)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      body.classList.remove('modal-open')
      window.removeEventListener('keydown', onKey)
    }
  }, [queueModal])

  useEffect(() => {
    if (!queueModal) return
    const t = window.setTimeout(() => {
      setDiscOffset(0)
      setDiscQ(discQInput.trim())
    }, 320)
    return () => window.clearTimeout(t)
  }, [discQInput, queueModal])

  useEffect(() => {
    setDiscSelected(new Set())
  }, [queueModal, discStatus, discReason, discQ])

  const openQueueModal = (kind: QueueBrowseKind) => {
    setDiscQInput('')
    setDiscQ('')
    setDiscReason('')
    setDiscReasons([])
    setDiscOffset(0)
    setDiscSelected(new Set())
    setDiscRequeueNote('')
    if (kind === 'discarded') setDiscStatus('failed')
    setQueueModal(kind)
  }

  // 与 ed2k 一致：开关开启即连续执行；进入页面时若已开则补启一次调度
  useEffect(() => {
    if (!status?.enabled) {
      autoLoopTried.current = false
      return
    }
    if (status.looping || status.running || busy || autoLoopTried.current) return
    autoLoopTried.current = true
    void (async () => {
      try {
        await startCrawlerLoop()
        await refresh()
      } catch {
        /* 权限或并发时忽略 */
      }
    })()
  }, [status?.enabled, status?.looping, status?.running, busy, refresh])

  const enabled = !!status?.enabled
  const running = !!status?.running
  const looping = !!status?.looping
  const loopKind = status?.loop_kind || (looping ? 'deep' : null)
  const stopping = !!status?.stopping
  const metrics = status?.metrics
  const queue = status?.queue
  const throttle = status?.throttle
  const activity = status?.activity || []

  const abnormal = Number(metrics?.queue_abnormal ?? queue?.abnormal ?? 0)
  const readyQueue = Number(metrics?.queue_ready ?? queue?.ready ?? 0)
  const discardedFailed = Number(
    metrics?.discarded_failed ?? status?.discarded?.failed ?? discCounts.failed ?? 0,
  )
  const discardedSkipped = Number(
    metrics?.discarded_skipped ?? status?.discarded?.skipped ?? discCounts.skipped ?? 0,
  )
  const discardedTotal = Number(
    metrics?.discarded_total ?? status?.discarded?.total ?? discardedFailed + discardedSkipped,
  )
  const discPageStart = discTotal === 0 ? 0 : discOffset + 1
  const discPageEnd = Math.min(discOffset + discItems.length, discTotal)
  const discHasPrev = discOffset > 0
  const discHasNext = discOffset + DISCARDED_PAGE < discTotal
  const modalMeta = queueModal ? QUEUE_MODAL_META[queueModal] : null
  const discActivity = (status?.activity || []).slice(0, 40)
  const searchPlaceholder =
    queueModal === 'stubs'
      ? 'hash / 标题 / 原因…'
      : queueModal === 'ready' || queueModal === 'abnormal'
        ? 'tid / 标题 / 错误…'
        : '标题…'
  const idColLabel = queueModal === 'stubs' ? 'hash' : 'tid'
  const rnd = status?.random_progress
  const randomActive = !!rnd?.active || (looping && loopKind === 'random_tid')
  const randomProbed = Number(rnd?.probed ?? metrics?.random_probed ?? 0)
  const randomBudget = Number(rnd?.probe_budget ?? metrics?.random_budget ?? 200)
  const randomImported = Number(rnd?.imported ?? metrics?.random_imported ?? 0)
  const randomSession = Number(rnd?.session_probed ?? metrics?.random_session ?? 0)
  const stubProg = status?.account_stub_progress
  const stubActive =
    !!stubProg?.active || (running && String(status?.phase || '') === 'account_stubs')
  const stubDone = Number(stubProg?.done ?? metrics?.stub_done ?? 0)
  const stubRemaining = Number(
    stubProg?.remaining ?? stubProg?.budget ?? metrics?.stub_remaining ?? metrics?.stub_budget ?? 0,
  )
  const stubUpgraded = Number(stubProg?.upgraded ?? metrics?.stub_upgraded ?? 0)
  const stubStill = Number(stubProg?.still_stub ?? 0)
  const stubFailed = Number(stubProg?.failed ?? 0)
  const delayCurrent = throttle?.fetch_delay_current ?? status?.request_delay
  const riskTripped = String(status?.last_result?.reason || '').includes('cooldown_tripped')
  const importsPerMin = Number(
    status?.import_rate?.per_minute ?? metrics?.imports_per_minute ?? 0,
  )
  const importRateWindow = Number(status?.import_rate?.window_sec ?? 60)

  // 账号爬占位后台跑：轮询进度刷新小字；结束后改成「结束」摘要，避免一直停在「进行中」
  useEffect(() => {
    if (stubActive) {
      stubWasActive.current = true
      setRunHint(
        formatStubHint({
          active: true,
          done: stubDone,
          remaining: stubRemaining,
          upgraded: stubUpgraded,
          still: stubStill,
          failed: stubFailed,
        }),
      )
      return
    }
    if (stubWasActive.current) {
      stubWasActive.current = false
      setRunHint(
        formatStubHint({
          active: false,
          done: stubDone,
          remaining: stubRemaining,
          upgraded: stubUpgraded,
          still: stubStill,
          failed: stubFailed,
        }),
      )
      return
    }
    // 页面刷新后：进度已结束但小字仍是旧的「进行中/启动中」
    if (
      stubDone > 0 &&
      /账号爬占位(中|启动中|进行中|已开始)|账号重爬(中|启动中|进行中|已开始)/.test(runHint)
    ) {
      setRunHint(
        formatStubHint({
          active: false,
          done: stubDone,
          remaining: stubRemaining,
          upgraded: stubUpgraded,
          still: stubStill,
          failed: stubFailed,
        }),
      )
    }
  }, [stubActive, stubDone, stubRemaining, stubUpgraded, stubStill, stubFailed, runHint])

  const onToggle = async (next: boolean) => {
    setBusy(true)
    try {
      if (next) {
        await setCrawlerEnabled(true)
        await startCrawlerLoop()
        toast.success('论坛爬虫已开启 · 连续执行')
      } else {
        // 与「手动停止」同一套：关开关 + 清理线程 + 队列不丢
        setRunHint('正在停止…')
        const res = await stopCrawler()
        autoLoopTried.current = false
        const line = res.forced
          ? '开关已关闭 · 已强制停止 · 队列已保留'
          : '开关已关闭 · 线程已退出 · 队列已保留'
        setRunHint(line)
        toast.info(line)
      }
      await refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '切换失败')
    } finally {
      setBusy(false)
    }
  }

  const onRun = async () => {
    if (enabled || looping || running || busy || stopping) {
      toast.info(enabled || looping ? '连续调度进行中，请先关闭开关' : '爬虫正在执行，请稍候')
      return
    }
    setBusy(true)
    setRunHint('爬取中，请稍候...')
    try {
      const res = await runCrawlerOnce()
      const r = res.result || {}
      if (r.skipped) {
        setRunHint(`跳过：${String(r.reason || '本轮未执行')}`)
        toast.info(String(r.reason || '本轮跳过'))
      } else if (r.ok === false) {
        setRunHint(`失败：${String(r.error || r.reason || '本轮失败')}`)
        toast.error(String(r.error || '本轮失败'))
      } else if (r.reason === 'stopped') {
        const line = `已停止：处理 ${r.crawled ?? 0} · 入库 ${r.imports ?? 0} · 队列已保留`
        setRunHint(line)
        toast.info(line)
      } else {
        const line = `完成：新帖 ${r.enqueued ?? r.discovered ?? 0} · 处理 ${r.crawled ?? 0} · 入库 ${r.imports ?? 0}`
        setRunHint(line)
        toast.success(line)
      }
      await refresh()
    } catch (err) {
      const msg = err instanceof Error ? err.message : '启动失败'
      setRunHint(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const onScanHead = async () => {
    if (enabled || looping || running || busy || stopping) {
      toast.info(enabled || looping ? '连续调度进行中，请先关闭开关' : '爬虫正在执行，请稍候')
      return
    }
    setBusy(true)
    setRunHint('扫新帖中，请稍候...')
    try {
      const res = await scanHeadOnce()
      const r = res.result || {}
      if (r.skipped) {
        setRunHint(`跳过：${String(r.reason || '本轮未执行')}`)
        toast.info(String(r.reason || '本轮跳过'))
      } else if (r.ok === false) {
        setRunHint(`失败：${String(r.error || r.reason || '本轮失败')}`)
        toast.error(String(r.error || '本轮失败'))
      } else if (r.reason === 'stopped') {
        const line = `已停止：新帖 ${r.enqueued ?? 0} · 处理 ${r.crawled ?? 0} · 队列已保留`
        setRunHint(line)
        toast.info(line)
      } else {
        const headN = Array.isArray(r.pages_head) ? r.pages_head.length : 0
        const line = `扫新帖完成：捕新 ${headN} 页 · 新入队 ${r.enqueued ?? r.discovered ?? 0} · 处理 ${r.crawled ?? 0}`
        setRunHint(line)
        toast.success(line)
      }
      await refresh()
    } catch (err) {
      const msg = err instanceof Error ? err.message : '扫新帖失败'
      setRunHint(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const onRandomTid = async () => {
    if (enabled || looping || running || busy || stopping) {
      toast.info(enabled || looping ? '连续调度进行中，请先关闭开关' : '爬虫正在执行，请稍候')
      return
    }
    setBusy(true)
    setRunHint('随机抓帖连续调度启动中…')
    try {
      const res = await startRandomTidLoop({ count: 200 })
      const probe = res.probe ?? 200
      const line =
        res.message === 'already'
          ? `随机抓帖连续调度已在运行 · 每轮 ${probe}`
          : `随机抓帖连续调度已启动 · 每轮 ${probe} · 不进队列 · 跳过已入库 · 停止后重新抽样`
      setRunHint(line)
      toast.success(line)
      await refresh()
    } catch (err) {
      const msg = err instanceof Error ? err.message : '随机抓帖启动失败'
      setRunHint(msg)
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const onStop = async () => {
    // 不弹确认、不因状态禁用：状态轮询失败时也要能停
    setRunHint('正在停止…')
    try {
      const res = await stopCrawler()
      autoLoopTried.current = false
      const line = res.forced
        ? '已强制停止 · 队列任务已保留'
        : '已停止 · 队列任务已保留'
      setRunHint(line)
      toast.success(line)
      await refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '停止失败')
    }
  }

  const onRetryAbnormal = async () => {
    if (abnormal <= 0) {
      toast.info('当前没有异常帖可重试')
      return
    }
    if (looping || running) {
      toast.info(looping ? '请先关闭连续调度' : '请等待当前任务结束')
      return
    }
    const ok = await confirmDialog({
      title: '异常重试',
      message: `重爬异常队列 ${abnormal} 条（含软文/拦截壳）；成功后才出队，失败仍留队。确定？`,
      confirmText: '开始重爬',
    })
    if (!ok) return
    setBusy(true)
    setRunHint('异常队列重爬中…')
    try {
      const res = await retryAbnormalQueue()
      if (res.message && res.message !== 'ok') {
        throw new Error(res.message === 'failed' ? '异常重试未执行（可能仍被停止标拦截）' : String(res.message))
      }
      const line = `异常重试：处理 ${res.crawled ?? 0} · 入库 ${res.imports ?? 0} · 仍重试 ${res.retries ?? 0}`
      setRunHint(line)
      toast.success(line)
      await refresh()
      await loadDiscarded()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '异常重试失败')
    } finally {
      setBusy(false)
    }
  }

  const canSelectDiscarded = queueModal === 'discarded'
  const pageSelectableTids = canSelectDiscarded
    ? discItems.map(rowTid).filter((t): t is number => t != null)
    : []
  const pageSelectedCount = pageSelectableTids.filter((t) => discSelected.has(t)).length
  const allPageSelected =
    pageSelectableTids.length > 0 && pageSelectedCount === pageSelectableTids.length
  const somePageSelected = pageSelectedCount > 0 && !allPageSelected

  const toggleDiscTid = (tid: number) => {
    setDiscSelected((prev) => {
      const next = new Set(prev)
      if (next.has(tid)) next.delete(tid)
      else next.add(tid)
      return next
    })
  }

  const toggleSelectPage = () => {
    setDiscSelected((prev) => {
      const next = new Set(prev)
      if (allPageSelected) {
        for (const tid of pageSelectableTids) next.delete(tid)
      } else {
        for (const tid of pageSelectableTids) next.add(tid)
      }
      return next
    })
  }

  const onSelectAllFiltered = async () => {
    if (!canSelectDiscarded || discSelectAllBusy || discRequeueBusy) return
    if (discTotal <= 0) {
      toast.info('当前筛选下没有可选项')
      return
    }
    setDiscSelectAllBusy(true)
    try {
      const res = await fetchDiscardedTids({
        status: discStatus,
        q: discQ || undefined,
        reason: discReason || undefined,
        limit: 2000,
      })
      const tids = (res.tids || []).filter((t) => Number.isFinite(t) && t > 0)
      setDiscSelected(new Set(tids))
      if (!tids.length) {
        toast.info('当前筛选下没有有效 tid')
      } else if (res.truncated) {
        toast.info(`已选前 ${tids.length} 条（共 ${res.total}，单次上限 ${res.limit}）`)
      } else {
        toast.success(`已全选当前筛选 ${tids.length} 条`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '全选筛选失败')
    } finally {
      setDiscSelectAllBusy(false)
    }
  }

  const onBatchRequeueSelected = async () => {
    if (!canSelectDiscarded || discRequeueBusy) return
    const tids = Array.from(discSelected)
    if (!tids.length) {
      toast.info('请先勾选要重爬的帖')
      return
    }
    const ok = await confirmDialog({
      title: '批量重爬',
      message: `将直接重爬选中的 ${tids.length} 条失败/跳过帖（不依赖当前板队列）。连续调度开启时仅入队。确定？`,
      confirmText: '重爬选中',
    })
    if (!ok) return
    setDiscRequeueBusy(true)
    setDiscRequeueNote('重爬进行中…')
    try {
      const res = await requeueDiscardedTids({ tids })
      const line = res.note || `已重新入队 ${res.requeued} 条`
      setRunHint(line)
      setDiscRequeueNote(line)
      if ((res.imports ?? 0) > 0 || (res.crawled ?? 0) > 0 || res.requeued > 0) {
        toast.success(line)
      } else {
        toast.info(line)
      }
      setDiscSelected(new Set())
      await refresh()
      await loadDiscarded()
    } catch (err) {
      const msg = err instanceof Error ? err.message : '批量重爬失败'
      setDiscRequeueNote(msg)
      toast.error(msg)
    } finally {
      setDiscRequeueBusy(false)
    }
  }

  const accessDeniedTitleCount = Number(
    metrics?.discarded_access_denied_title ?? discKindCounts.access_denied_bad_title ?? 0,
  )
  const discardedFailedKindCount = Number(
    metrics?.discarded_failed_kind ?? discKindCounts.failed_all ?? 0,
  )
  const priorityStubCount = Number(metrics?.priority_stubs ?? 0)
  const accountPassTotal = Number(
    metrics?.account_pass_total ??
      priorityStubCount + accessDeniedTitleCount + discardedFailedKindCount,
  )

  const onRecrawlStubs = async () => {
    if (enabled || looping || running) {
      toast.info(
        enabled || looping ? '请先关闭连续调度后再账号重爬' : '请等待当前任务结束',
      )
      return
    }
    const ok = await confirmDialog({
      title: '账号重爬',
      message:
        `用账号 Cookie 依次处理：① 未处理「失败」${discardedFailedKindCount} 条；` +
        `② 未处理「无阅读权限」跳过 ${accessDeniedTitleCount} 条；` +
        `③ 资源库优先占位 ${priorityStubCount} 条（合计 ${accountPassTotal}）。` +
        `不限数量直至跑完。升级成功会删旧占位；登录后需回复/需购买则跳过并删占位。需先配置账号 Cookie。确定？`,
      confirmText: '开始重爬',
    })
    if (!ok) return
    setBusy(true)
    stubWasActive.current = true
    setRunHint('账号重爬启动中…')
    try {
      const res = await recrawlAccountStubs()
      if (res.started) {
        const disc = Number(res.discarded_remaining ?? 0)
        const stubs = Number(res.stub_remaining ?? res.remaining ?? res.budget ?? 0)
        const total = Number(res.remaining ?? res.budget ?? stubs + disc)
        const line =
          `账号重爬进行中：已处理 0 · 库内剩余 ${total}` +
          (disc > 0 ? `（含未处理失败/无权跳过 ${disc}）` : '')
        setRunHint(line)
        toast.success(
          `账号重爬已开始 · 共 ${total}` +
            (disc > 0 ? ` · 未处理 ${disc}` : '') +
            (stubs > 0 && disc > 0 ? ` · 占位 ${stubs}` : ''),
        )
      } else {
        stubWasActive.current = false
        const line = res.note || res.message || '无优先占位 / 未处理失败·无权跳过可处理'
        setRunHint(line)
        toast.info(line)
      }
      await refresh()
      await loadDiscarded()
    } catch (err) {
      stubWasActive.current = false
      toast.error(err instanceof Error ? err.message : '账号重爬失败')
    } finally {
      setBusy(false)
    }
  }

  const forumName = status?.active_forum_name || status?.active_forum_id || '论坛'

  const runLabel = (() => {
    if (loading) return '读取中…'
    if (stopping || (running && !enabled && loopKind !== 'random_tid')) return `正在停止 · ${forumName}`
    if (stopping) return `正在停止 · ${forumName}`
    if (riskTripped) return `${forumName} · 风控熔断`
    if (looping && loopKind === 'random_tid') return `随机抓帖连续中 · 每轮 200 · ${forumName}`
    if (running || looping) return `正在执行 · ${forumName}`
    if (enabled) return `${forumName} · 已开启 · 连续执行`
    return `${forumName} · 已关闭`
  })()

  const resultLine = formatResultLine(status, runHint)

  return (
    <section className="page page-crawler active">
      <div className="page-scroll">
        <div className="card block crawler-live">
            <div className="crawler-toolbar">
              <div className="crawler-toolbar-top">
                <div className="crawler-toolbar-left">
                  <label className="crawler-switch" title="开启/关闭论坛爬虫">
                    <input
                      type="checkbox"
                      checked={enabled}
                      disabled={busy || loading}
                      onChange={(e) => void onToggle(e.target.checked)}
                    />
                    <span className="crawler-switch-slider" aria-hidden />
                  </label>
                  <span className="crawler-run-label">{runLabel}</span>
                </div>
                <button
                  type="button"
                  className="crawler-refresh"
                  disabled={busy}
                  title="刷新状态与活动日志"
                  onClick={() => {
                    void refresh()
                    if (queueModal) void loadDiscarded()
                  }}
                >
                  刷新
                </button>
              </div>
              <div className="crawler-toolbar-right">
                <div className="crawler-actions" role="group" aria-label="爬虫操作">
                  <button
                    type="button"
                    className="crawler-action crawler-action-primary"
                    disabled={enabled || looping || running || busy || stopping}
                    title={
                      enabled || looping
                        ? '连续调度进行中，请先关闭开关后再立即爬取'
                        : running || stopping
                          ? '本轮仍在执行，请稍候'
                          : '执行一轮爬虫（深扫列表 → 已有只改板块 · 缺失抓帖入库）'
                    }
                    onClick={() => void onRun()}
                  >
                    {running || looping || enabled ? '执行中…' : '立即爬取'}
                  </button>
                  <button
                    type="button"
                    className="crawler-action"
                    disabled={enabled || looping || running || busy || stopping}
                    title={
                      enabled || looping
                        ? '连续调度进行中，请先关闭开关后再扫新帖'
                        : running || stopping
                          ? '本轮仍在执行，请稍候'
                          : '启用子板按序捕新（强制读列表）→ 收尾消化待抓至空；连续全旧帖早停；可手动停止'
                    }
                    onClick={() => void onScanHead()}
                  >
                    扫新帖
                  </button>
                  <button
                    type="button"
                    className="crawler-action"
                    disabled={enabled || looping || running || busy || stopping}
                    title={
                      enabled || looping
                        ? '连续调度进行中，请先关闭开关后再随机抓帖'
                        : running || stopping
                          ? '本轮仍在执行，请稍候'
                          : '循环模式：每轮随机 200 个 tid 直链探测并入库；不写待抓队列；跳过已入库；停止后清空本会话抽样，下次重新生成'
                    }
                    onClick={() => void onRandomTid()}
                  >
                    随机抓帖
                  </button>
                  <button
                    type="button"
                    className="crawler-action"
                    disabled={enabled || looping || running || busy || stopping}
                    title={
                      enabled || looping
                        ? '连续调度进行中，请先关闭开关后再账号重爬'
                        : running || stopping
                          ? '本轮仍在执行，请稍候'
                          : accountPassTotal > 0
                            ? `用账号 Cookie：失败 ${discardedFailedKindCount} + 无阅读权限跳过 ${accessDeniedTitleCount} + 优先占位 ${priorityStubCount} = ${accountPassTotal}；请先配置账号 Cookie`
                            : '用账号 Cookie 重爬未处理失败、无阅读权限跳过与优先占位；登录后需回复/需购买会跳过。请先配置账号 Cookie'
                    }
                    onClick={() => void onRecrawlStubs()}
                  >
                    账号重爬
                    {accountPassTotal > 0 ? (
                      <span className="crawler-action-badge">{accountPassTotal}</span>
                    ) : null}
                  </button>
                  <button
                    type="button"
                    className={`crawler-action${abnormal > 0 ? ' crawler-action-warn' : ''}`}
                    disabled={busy || looping || running || abnormal <= 0}
                    title={
                      looping
                        ? '连续调度进行中，请先关闭'
                        : running
                          ? '请等待当前任务结束'
                          : abnormal > 0
                            ? `重爬异常队列 ${abnormal} 条（含软文/拦截壳），成功才出队`
                            : '暂无异常帖'
                    }
                    onClick={() => void onRetryAbnormal()}
                  >
                    异常重试
                    {abnormal > 0 ? <span className="crawler-action-badge">{abnormal}</span> : null}
                  </button>
                  <button
                    type="button"
                    className="crawler-action crawler-action-danger"
                    disabled={false}
                    title="立即停止（始终可点；主接口不通时自动走紧急旁路）"
                    onClick={() => void onStop()}
                  >
                    {stopping ? '停止中…' : '手动停止'}
                  </button>
                </div>
              </div>
            </div>

            <div className="crawler-overview">
              <div className="crawler-overview-row">
                <div className="crawler-overview-metrics">
                  <button
                    type="button"
                    className="metric-pill metric-pill-btn"
                    title="失败/重试贴（含软文拦截壳）。点此查看明细；也可用「异常重试」重爬"
                    onClick={() => openQueueModal('abnormal')}
                  >
                    <span className="metric-val stat-warn">{abnormal}</span>
                    <span className="metric-lbl">异常帖</span>
                  </button>
                  <button
                    type="button"
                    className="metric-pill metric-pill-btn"
                    title="启用子板全部「尚未失败」的待抓帖合计。点此查看明细"
                    onClick={() => openQueueModal('ready')}
                  >
                    <span className="metric-val">{readyQueue}</span>
                    <span className="metric-lbl">正常队列</span>
                  </button>
                  <button
                    type="button"
                    className="metric-pill metric-pill-btn"
                    title="入队后最终失败或跳过（非入库/占位）。点此查看明细"
                    onClick={() => openQueueModal('discarded')}
                  >
                    <span className={`metric-val${discardedTotal > 0 ? ' stat-failed' : ''}`}>
                      {discardedTotal}
                    </span>
                    <span className="metric-lbl">未处理</span>
                  </button>
                  <span
                    className={`metric-pill${randomActive ? ' metric-pill-random' : ''}`}
                    title={
                      randomActive
                        ? `随机抓取进行中：本轮 ${randomProbed}/${randomBudget} · 入库 ${randomImported} · 本会话已探 ${randomSession}（不进待抓队列）`
                        : `随机抓取进度（空闲）。启动后显示本轮已探/配额；入库 ${randomImported} · 会话 ${randomSession}`
                    }
                  >
                    <span className={`metric-val${randomActive ? ' stat-ok' : ''}`}>
                      {randomProbed}/{randomBudget}
                    </span>
                    <span className="metric-lbl">随机进度</span>
                  </span>
                  <button
                    type="button"
                    className={`metric-pill metric-pill-btn${stubActive ? ' metric-pill-stub' : ''}`}
                    title={
                      stubActive
                        ? `账号重爬进行中：已处理 ${stubDone} · 库内剩余 ${stubRemaining} · 升级 ${stubUpgraded} · 仍占位 ${stubStill} · 失败 ${stubFailed}`
                        : `合计 ${accountPassTotal}（失败 ${discardedFailedKindCount} + 无阅读权限跳过 ${accessDeniedTitleCount} + 优先占位 ${priorityStubCount}）。点此查看占位明细`
                    }
                    onClick={() => openQueueModal('stubs')}
                  >
                    <span className={`metric-val${stubActive ? ' stat-ok' : ''}`}>
                      {stubActive || stubDone > 0 || stubRemaining > 0 || accountPassTotal > 0
                        ? stubActive || stubDone > 0
                          ? `${stubDone}/剩${stubRemaining}`
                          : String(accountPassTotal)
                        : '—'}
                    </span>
                    <span className="metric-lbl">重爬进度</span>
                  </button>
                  {riskTripped ? (
                    <span className="metric-pill metric-pill-risk">
                      <span className="metric-val stat-failed">熔断</span>
                      <span className="metric-lbl">风控状态</span>
                    </span>
                  ) : null}
                  {delayCurrent != null ? (
                    <span className="metric-pill metric-pill-delay">
                      <span className="metric-val">{delayCurrent}s</span>
                      <span className="metric-lbl">当前请求延迟</span>
                    </span>
                  ) : null}
                  <span
                    className={`metric-pill metric-pill-rate${importsPerMin > 0 ? ' is-live' : ''}`}
                    title={`近 ${importRateWindow} 秒滚动窗口内入库+占位帖数`}
                  >
                    <span className="metric-val" key={importsPerMin}>
                      {importsPerMin}
                      <span className="metric-rate-unit">/分</span>
                    </span>
                    <span className="metric-lbl">入库速度</span>
                  </span>
                </div>
              </div>
            </div>

            <p className="hint crawler-result">{resultLine}</p>

            <div className="activity-log-wrap">
              <div className="activity-log">
                {activity.length ? (
                  activity.map((a, i) => (
                    <div key={`${a.t}-${i}-${a.msg}`} className={`activity-row ${activityLevelClass(a.msg)}`}>
                      <span className="activity-time">{a.t || '—'}</span>
                      <span className="activity-msg">
                        <ActivityMsg msg={a.msg} webCrawlUrls={status?.web_crawl_urls} />
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="activity-empty">
                    {enabled
                      ? '暂无活动日志 · 点「立即爬取」或等待连续调度'
                      : '暂无活动日志 · 点「立即爬取」「扫新帖」或明细里「重爬选中」后会出现'}
                  </div>
                )}
              </div>
            </div>

          </div>
      </div>

      {queueModal && modalMeta ? (
        <div
          className="modal-backdrop crawler-discarded-backdrop"
          role="presentation"
          onClick={() => setQueueModal(null)}
        >
          <div
            className="modal-card crawler-discarded-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="crawler-queue-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head crawler-discarded-modal-head">
              <div className="crawler-discarded-title">
                <h3 id="crawler-queue-modal-title">{modalMeta.title}</h3>
                <span className="crawler-discarded-sub">{modalMeta.sub}</span>
              </div>
              <button
                type="button"
                className="btn ghost sm icon-only"
                title="关闭"
                onClick={() => setQueueModal(null)}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="crawler-discarded-modal-body">
              <div className="crawler-discarded-tools">
                {queueModal === 'discarded' ? (
                  <div className="crawler-discarded-tabs" role="tablist" aria-label="未处理筛选">
                    {(
                      [
                        ['failed', `失败 ${discardedFailed}`],
                        ['skipped', `跳过 ${discardedSkipped}`],
                        ['all', `全部 ${discardedTotal}`],
                      ] as const
                    ).map(([id, label]) => (
                      <button
                        key={id}
                        type="button"
                        role="tab"
                        aria-selected={discStatus === id}
                        className={`crawler-discarded-tab${discStatus === id ? ' active' : ''}`}
                        onClick={() => {
                          setDiscStatus(id)
                          setDiscReason('')
                          setDiscOffset(0)
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="crawler-discarded-tools-row">
                  <input
                    type="search"
                    className="crawler-discarded-search"
                    placeholder={searchPlaceholder}
                    value={discQInput}
                    onChange={(e) => setDiscQInput(e.target.value)}
                    enterKeyHint="search"
                  />
                  {canSelectDiscarded ? (
                    <>
                      <button
                        type="button"
                        className="crawler-action crawler-action-muted"
                        disabled={
                          discSelectAllBusy ||
                          discRequeueBusy ||
                          discLoading ||
                          discTotal <= 0
                        }
                        title={
                          discTotal > 0
                            ? `按当前筛选（状态/搜索/原因）全选全部页，共约 ${discTotal} 条`
                            : '当前筛选无记录'
                        }
                        onClick={() => void onSelectAllFiltered()}
                      >
                        {discSelectAllBusy
                          ? '全选中…'
                          : discSelected.size > 0 && discSelected.size >= discTotal
                            ? `已全选 ${discSelected.size}`
                            : `全选筛选${discTotal > 0 ? ` ${discTotal}` : ''}`}
                      </button>
                      <button
                        type="button"
                        className="crawler-action"
                        disabled={discRequeueBusy || discSelected.size === 0}
                        title={
                          discSelected.size
                            ? `重爬已勾选 ${discSelected.size} 条`
                            : '先勾选要重爬的帖'
                        }
                        onClick={() => void onBatchRequeueSelected()}
                      >
                        {discRequeueBusy
                          ? '重爬中…'
                          : discSelected.size
                            ? `重爬选中 ${discSelected.size}`
                            : '重爬选中'}
                      </button>
                    </>
                  ) : null}
                  <button
                    type="button"
                    className="crawler-action crawler-action-muted"
                    disabled={discLoading || discRequeueBusy}
                    title="刷新明细"
                    onClick={() => void loadDiscarded()}
                  >
                    {discLoading ? '读取中…' : '刷新'}
                  </button>
                </div>
                <select
                  className="crawler-discarded-reason-filter crawler-discarded-reason-filter-bar"
                  value={discReason}
                  title={`按${modalMeta.reasonLabel}筛选`}
                  aria-label={`按${modalMeta.reasonLabel}筛选`}
                  onChange={(e) => {
                    setDiscReason(e.target.value)
                    setDiscOffset(0)
                  }}
                >
                  <option value="">全部{modalMeta.reasonLabel}</option>
                  {discReasons.map((item) => (
                    <option key={item.reason} value={item.reason}>
                      {item.reason}（{item.count}）
                    </option>
                  ))}
                  {discReason && !discReasons.some((item) => item.reason === discReason) ? (
                    <option value={discReason}>{discReason}</option>
                  ) : null}
                </select>
              </div>

              <div className={`crawler-discarded-table-wrap desktop-only${discLoading ? ' is-loading' : ''}`}>
                <table className="crawler-discarded-table">
                  <thead>
                    <tr>
                      {canSelectDiscarded ? (
                        <th className="crawler-discarded-check-th">
                          <input
                            type="checkbox"
                            className="crawler-discarded-check"
                            checked={allPageSelected}
                            ref={(el) => {
                              if (el) el.indeterminate = somePageSelected
                            }}
                            disabled={!pageSelectableTids.length || discRequeueBusy}
                            onChange={toggleSelectPage}
                            aria-label="全选本页"
                            title="仅全选本页；跨页请用「全选筛选」"
                          />
                        </th>
                      ) : null}
                      <th>时间</th>
                      <th>状态</th>
                      <th>板块</th>
                      <th>{idColLabel}</th>
                      <th>标题</th>
                      {queueModal === 'stubs' ? null : <th>重试</th>}
                      <th>{modalMeta.reasonLabel}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {discItems.length ? (
                      discItems.map((row, idx) => {
                        const url = rowUrl(row)
                        const st = rowStatus(row, queueModal)
                        const title = rowTitle(row)
                        const reason = discardedReason(row)
                        const tid = rowTid(row)
                        const idText =
                          queueModal === 'stubs'
                            ? (row.hash || '').slice(0, 12) || '—'
                            : row.tid || '—'
                        const rowKey = url || row.hash || `${idx}-${idText}`
                        const checked = tid != null && discSelected.has(tid)
                        return (
                          <tr
                            key={rowKey}
                            className={checked ? 'is-selected' : undefined}
                            onClick={
                              canSelectDiscarded && tid != null
                                ? (e) => {
                                    const t = e.target as HTMLElement
                                    if (t.closest('a, input, button, label')) return
                                    toggleDiscTid(tid)
                                  }
                                : undefined
                            }
                          >
                            {canSelectDiscarded ? (
                              <td className="crawler-discarded-check-td">
                                <input
                                  type="checkbox"
                                  className="crawler-discarded-check"
                                  checked={checked}
                                  disabled={tid == null || discRequeueBusy}
                                  onChange={() => {
                                    if (tid != null) toggleDiscTid(tid)
                                  }}
                                  aria-label={tid != null ? `选择 tid ${tid}` : '不可选'}
                                />
                              </td>
                            ) : null}
                            <td className="mono">
                              {formatWhen(row.crawled_at || row.updated_at)}
                            </td>
                            <td>
                              <span
                                className={`crawler-discarded-badge ${
                                  st === 'failed'
                                    ? 'is-failed'
                                    : st === 'pending' || st === 'stub'
                                      ? 'is-skipped'
                                      : 'is-skipped'
                                }`}
                              >
                                {STATUS_LABEL[st] || st}
                              </span>
                            </td>
                            <td title={row.board_fid || ''}>
                              {row.board_name || row.board_fid || '—'}
                            </td>
                            <td className="mono">
                              {url && idText !== '—' ? (
                                <a href={url} target="_blank" rel="noreferrer" title={url}>
                                  {idText}
                                </a>
                              ) : (
                                idText
                              )}
                            </td>
                            <td className="crawler-discarded-title-cell" title={title}>
                              {title}
                            </td>
                            {queueModal === 'stubs' ? null : (
                              <td className="mono">{row.fetch_fail_count ?? 0}</td>
                            )}
                            <td className="crawler-discarded-reason" title={reason}>
                              {reason}
                            </td>
                          </tr>
                        )
                      })
                    ) : (
                      <tr>
                        <td
                          colSpan={
                            (queueModal === 'stubs' ? 6 : 7) + (canSelectDiscarded ? 1 : 0)
                          }
                          className="crawler-discarded-empty"
                        >
                          {discLoading ? '加载中…' : '暂无记录'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div
                className={`crawler-discarded-cards mobile-only${discLoading ? ' is-loading' : ''}`}
              >
                {discItems.length ? (
                  discItems.map((row, idx) => {
                    const url = rowUrl(row)
                    const st = rowStatus(row, queueModal)
                    const title = rowTitle(row)
                    const reason = discardedReason(row)
                    const tid = rowTid(row)
                    const idText =
                      queueModal === 'stubs'
                        ? (row.hash || '').slice(0, 12) || '—'
                        : row.tid || '—'
                    const rowKey = url || row.hash || `m-${idx}-${idText}`
                    const checked = tid != null && discSelected.has(tid)
                    return (
                      <article
                        key={rowKey}
                        className={`crawler-discarded-card${checked ? ' is-selected' : ''}`}
                        onClick={
                          canSelectDiscarded && tid != null
                            ? (e) => {
                                const t = e.target as HTMLElement
                                if (t.closest('a, input, button, label')) return
                                toggleDiscTid(tid)
                              }
                            : undefined
                        }
                      >
                        <div className="crawler-discarded-card-top">
                          {canSelectDiscarded ? (
                            <input
                              type="checkbox"
                              className="crawler-discarded-check"
                              checked={checked}
                              disabled={tid == null || discRequeueBusy}
                              onChange={() => {
                                if (tid != null) toggleDiscTid(tid)
                              }}
                              aria-label={tid != null ? `选择 tid ${tid}` : '不可选'}
                            />
                          ) : null}
                          <span
                            className={`crawler-discarded-badge ${
                              st === 'failed' ? 'is-failed' : 'is-skipped'
                            }`}
                          >
                            {STATUS_LABEL[st] || st}
                          </span>
                          <time className="mono crawler-discarded-card-time">
                            {formatWhen(row.crawled_at || row.updated_at)}
                          </time>
                        </div>
                        <h4 className="crawler-discarded-card-title">{title}</h4>
                        <div className="crawler-discarded-card-meta">
                          <span className="crawler-discarded-card-board">
                            {row.board_name || row.board_fid || '—'}
                          </span>
                          {url && idText !== '—' ? (
                            <a
                              className="mono crawler-discarded-card-id"
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {idColLabel} {idText}
                            </a>
                          ) : (
                            <span className="mono crawler-discarded-card-id">
                              {idColLabel} {idText}
                            </span>
                          )}
                          {queueModal === 'stubs' ? null : (
                            <span className="crawler-discarded-card-retry">
                              重试 {row.fetch_fail_count ?? 0}
                            </span>
                          )}
                        </div>
                        <p className="crawler-discarded-card-reason">{reason}</p>
                      </article>
                    )
                  })
                ) : (
                  <div className="crawler-discarded-empty">
                    {discLoading ? '加载中…' : '暂无记录'}
                  </div>
                )}
              </div>

              {canSelectDiscarded ? (
                <div className="crawler-discarded-log">
                  {discRequeueNote ? (
                    <p className="crawler-discarded-log-note">{discRequeueNote}</p>
                  ) : null}
                  <div className="crawler-discarded-log-head">重爬日志</div>
                  <div className="crawler-discarded-log-body activity-log">
                    {discActivity.length ? (
                      discActivity.map((a, i) => (
                        <div
                          key={`disc-${a.t}-${i}-${a.msg}`}
                          className={`activity-row ${activityLevelClass(a.msg)}`}
                        >
                          <span className="activity-time">{a.t || '—'}</span>
                          <span className="activity-msg">
                            <ActivityMsg msg={a.msg} webCrawlUrls={status?.web_crawl_urls} />
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="activity-empty">
                        {discRequeueBusy
                          ? '重爬进行中，日志稍后出现…'
                          : '暂无活动日志 · 勾选后点「重爬选中」，进度会显示在这里'}
                      </div>
                    )}
                  </div>
                </div>
              ) : null}

              <div className="crawler-discarded-foot">
                <span className="toolbar-meta">
                  {discTotal === 0
                    ? '共 0 条'
                    : `第 ${discPageStart}–${discPageEnd} 条，共 ${discTotal} 条`}
                  {canSelectDiscarded && discSelected.size > 0
                    ? ` · 已选 ${discSelected.size}`
                    : ''}
                </span>
                <div className="crawler-discarded-pager">
                  {canSelectDiscarded && discSelected.size > 0 ? (
                    <button
                      type="button"
                      className="crawler-action crawler-action-muted"
                      disabled={discRequeueBusy}
                      onClick={() => setDiscSelected(new Set())}
                    >
                      清除选中
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="crawler-action crawler-action-muted"
                    disabled={!discHasPrev || discLoading || discRequeueBusy}
                    onClick={() => setDiscOffset((v) => Math.max(0, v - DISCARDED_PAGE))}
                  >
                    上一页
                  </button>
                  <button
                    type="button"
                    className="crawler-action crawler-action-muted"
                    disabled={!discHasNext || discLoading || discRequeueBusy}
                    onClick={() => setDiscOffset((v) => v + DISCARDED_PAGE)}
                  >
                    下一页
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
