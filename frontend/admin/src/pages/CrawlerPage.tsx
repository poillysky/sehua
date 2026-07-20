import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fetchCrawlerStatus,
  recrawlAccountStubs,
  retryAbnormalQueue,
  runCrawlerOnce,
  scanHeadOnce,
  setCrawlerEnabled,
  startCrawlerLoop,
  startRandomTidLoop,
  stopCrawler,
  type CrawlerStatus,
} from '../api/crawler'
import { confirmDialog } from '../ui/confirm'
import { toast } from '../ui/toast'

function activityLevelClass(msg: string): string {
  const m = msg || ''
  // 「失败 0」只是汇总计数，不当错误
  const failCount = m.match(/失败\s*(\d+)/)
  const zeroFail = failCount ? Number(failCount[1]) === 0 : false
  // 成功：绿（优先于「异常队列」等词）
  if (
    m.includes('本轮结束') ||
    m.includes('已启动') ||
    m.includes('已开启') ||
    m.includes('进站就绪') ||
    m.includes('正常入库') ||
    m.includes('占位入库') ||
    m.includes('已入库重爬结束') ||
    m.includes('已入库批量重爬结束') ||
    (m.includes('已入库批量重爬') && zeroFail) ||
    m.includes('扫新帖完成') ||
    m.includes('改板块') ||
    m.includes('随机入库') ||
    m.includes('随机抓帖结束') ||
    m.includes('随机抓帖本轮结束') ||
    m.includes('随机抓帖连续调度已启动') ||
    m.includes('本批入库已达上限') ||
    m.includes('账号爬占位结束') ||
    m.includes('账号爬占位升级') ||
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
    m.includes('停板') ||
    m.includes('错误') ||
    (m.includes('失败') && !zeroFail && !m.includes('成功才出队'))
  ) {
    return 'activity-error'
  }
  // 普通信息：白
  return 'activity-info'
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
      `账号爬占位进行中：已处理 ${p.done} · 库内剩余 ${p.remaining}` +
      ` · 升级 ${p.upgraded} · 仍占位 ${p.still} · 失败 ${p.failed}`
    )
  }
  return (
    `账号爬占位结束：处理 ${p.done} · 升级 ${p.upgraded}` +
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

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => {
      void refresh()
    }, 2000)
    return () => window.clearInterval(timer)
  }, [refresh])

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
      /账号爬占位(中|启动中|进行中|已开始)/.test(runHint)
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
    if (!running && !looping && !enabled) {
      toast.info('当前没有在跑的爬虫')
      return
    }
    const ok = await confirmDialog({
      title: '手动停止',
      message: '立即停止爬虫并清理线程。未处理完的队列任务会保留在数据库中，不会丢失。',
      confirmText: '停止',
    })
    if (!ok) return
    setBusy(true)
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
    } finally {
      setBusy(false)
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
      const line = `异常重试：处理 ${res.crawled ?? 0} · 入库 ${res.imports ?? 0} · 仍重试 ${res.retries ?? 0}`
      setRunHint(line)
      toast.success(line)
      await refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '异常重试失败')
    } finally {
      setBusy(false)
    }
  }

  const onRecrawlStubs = async () => {
    if (enabled || looping || running) {
      toast.info(
        enabled || looping ? '请先关闭连续调度后再账号爬占位' : '请等待当前任务结束',
      )
      return
    }
    const ok = await confirmDialog({
      title: '账号爬占位',
      message:
        '用账号 Cookie 重爬全部优先占位（需登录 / 无阅读权限 / 无权限下载附件），不限数量直至跑完。升级成功会删旧占位；若登录后为需回复/需购买则跳过并删占位。需先配置账号 Cookie。确定？',
      confirmText: '开始爬取',
    })
    if (!ok) return
    setBusy(true)
    stubWasActive.current = true
    setRunHint('账号爬占位启动中…')
    try {
      const res = await recrawlAccountStubs()
      if (res.started) {
        const line = `账号爬占位进行中：已处理 0 · 库内剩余 ${res.remaining ?? res.budget ?? 0}`
        setRunHint(line)
        toast.success(`账号爬占位已开始 · 队列 ${res.remaining ?? res.budget ?? 0}`)
      } else {
        stubWasActive.current = false
        const line = res.note || res.message || '无优先占位可处理'
        setRunHint(line)
        toast.info(line)
      }
      await refresh()
    } catch (err) {
      stubWasActive.current = false
      toast.error(err instanceof Error ? err.message : '账号爬占位失败')
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
                  onClick={() => void refresh()}
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
                          : '从第 1 页捕新入队（启用多板按序轮换；连续 2 页全已知或达上限后换下一板）'
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
                        ? '连续调度进行中，请先关闭开关后再账号爬占位'
                        : running || stopping
                          ? '本轮仍在执行，请稍候'
                          : '用账号 Cookie 重爬优先占位（不限数量）：需登录 / 无阅读权限 / 无权限下载附件；登录后需回复/需购买会跳过。请先配置账号 Cookie'
                    }
                    onClick={() => void onRecrawlStubs()}
                  >
                    账号爬占位
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
                    disabled={busy || stopping || (!running && !looping && !enabled)}
                    title="停止爬虫并清理线程；未完成队列保留不丢"
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
                  <span className="metric-pill" title="失败/重试贴（含软文拦截壳）；点「异常重试」在本队列重爬，成功才出队；到期后连续调度也会吃">
                    <span className="metric-val stat-warn">{abnormal}</span>
                    <span className="metric-lbl">异常帖</span>
                  </span>
                  <span className="metric-pill" title="启用子板全部「尚未失败」的待抓帖合计（实时）。连续调度多子板时不再只显示当前板，避免切板瞬间变成 0 却仍在入库">
                    <span className="metric-val">{readyQueue}</span>
                    <span className="metric-lbl">正常队列</span>
                  </span>
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
                  <span
                    className={`metric-pill${stubActive ? ' metric-pill-stub' : ''}`}
                    title={
                      stubActive
                        ? `账号爬占位进行中：已处理 ${stubDone} · 库内剩余 ${stubRemaining} · 升级 ${stubUpgraded} · 仍占位 ${stubStill} · 失败 ${stubFailed}` +
                          (stubProg?.current_tid
                            ? ` · 当前 tid=${stubProg.current_tid}${stubProg.current_title ? ` ${stubProg.current_title}` : ''}`
                            : '')
                        : stubDone > 0 || stubRemaining > 0
                          ? `上次：已处理 ${stubDone} · 库内剩余 ${stubRemaining} · 升级 ${stubUpgraded} · 仍占位 ${stubStill} · 失败 ${stubFailed}`
                          : '账号爬占位进度（空闲）。点「账号爬占位」后显示已处理与库内剩余'
                    }
                  >
                    <span className={`metric-val${stubActive ? ' stat-ok' : ''}`}>
                      {stubActive || stubDone > 0 || stubRemaining > 0
                        ? `${stubDone}/剩${stubRemaining}`
                        : '—'}
                    </span>
                    <span className="metric-lbl">占位进度</span>
                  </span>
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
                      <span className="activity-msg">{a.msg}</span>
                    </div>
                  ))
                ) : (
                  <div className="activity-empty">
                    {enabled ? '暂无活动日志 · 点「立即爬取」或等待连续调度' : '暂无活动日志 · 开启论坛爬虫后开始执行'}
                  </div>
                )}
              </div>
            </div>
          </div>
      </div>
    </section>
  )
}
