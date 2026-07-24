import { Fragment, useMemo, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { ForumBoard, ForumCrawlerConfig, ForumItem } from '../api/forums'

export type TopoStepId =
  | 'switch'
  | 'scheduler'
  | 'board_select'
  | 'session'
  | 'list_scan'
  | 'thread_crawl'
  | 'import'
  | 'random_tid'
  | 'account_stub'

type PipelineNode = {
  id: TopoStepId
  label: string
  detail: string
  status: 'idle' | 'ready' | 'active'
}

type Props = {
  forum: ForumItem & { crawler_config: ForumCrawlerConfig }
  activeForumId: string
  boards: ForumBoard[]
  activeBoardFid: string
}

const STEP_IDS: TopoStepId[] = [
  'switch',
  'scheduler',
  'board_select',
  'session',
  'list_scan',
  'thread_crawl',
  'import',
  'random_tid',
  'account_stub',
]

function parseStep(value: string | null): TopoStepId {
  return STEP_IDS.includes(value as TopoStepId) ? (value as TopoStepId) : 'switch'
}

function Process({ text, sub }: { text: string; sub?: string }) {
  return (
    <div className="fc-node fc-process">
      <span className="fc-text">{text}</span>
      {sub ? <span className="fc-sub">{sub}</span> : null}
    </div>
  )
}

function Decision({ text }: { text: string }) {
  return (
    <div className="fc-node fc-decision">
      <span className="fc-text">{text}</span>
    </div>
  )
}

function Terminal({
  text,
  sub,
  kind = 'muted',
}: {
  text: string
  sub?: string
  kind?: 'muted' | 'ok' | 'warn' | 'fail'
}) {
  return (
    <div className={`fc-node fc-terminal fc-terminal--${kind}`}>
      <span className="fc-text">{text}</span>
      {sub ? <span className="fc-sub">{sub}</span> : null}
    </div>
  )
}

function ArrowDown({ sm }: { sm?: boolean }) {
  return <div className={`fc-arrow fc-arrow-down${sm ? ' fc-arrow-down--sm' : ''}`} aria-hidden />
}

function ArrowRight() {
  return <div className="fc-arrow fc-arrow-right" aria-hidden />
}

function Spine({ children }: { children: ReactNode }) {
  return <div className="fc-spine">{children}</div>
}

function Branch({ label, main, children }: { label: string; main?: boolean; children: ReactNode }) {
  return (
    <div className={`fc-branch${main ? ' fc-branch--main' : ''}`}>
      <div className="fc-branch-stem" aria-hidden />
      <span className="fc-branch-label">{label}</span>
      <ArrowDown sm />
      <div className="fc-branch-body">{children}</div>
    </div>
  )
}

function Junction({ children, pair, cols }: { children: ReactNode; pair?: boolean; cols?: 2 | 3 | 4 }) {
  const colCls =
    pair || cols === 3
      ? ' fc-split-grid--3'
      : cols === 4
        ? ' fc-split-grid--4'
        : cols === 2
          ? ' fc-split-grid--2'
          : ''
  const pairCls = pair ? ' fc-split-grid--pair' : ''
  return (
    <div className={`fc-split-grid${colCls}${pairCls}`}>
      <div className="fc-split-bar" aria-hidden />
      {children}
    </div>
  )
}

function ChartShell({ hint, children }: { hint: string; children: ReactNode }) {
  return (
    <div className="fc-chart-wrap">
      <div className="fc-legend" aria-hidden>
        <span className="fc-legend-item">
          <i className="fc-legend-shape fc-legend-process" />
          处理步骤
        </span>
        <span className="fc-legend-item">
          <i className="fc-legend-shape fc-legend-decision" />
          条件判断
        </span>
        <span className="fc-legend-item">
          <i className="fc-legend-shape fc-legend-terminal" />
          流程结果
        </span>
      </div>
      <p className="fc-chart-hint">{hint}</p>
      <div className="fc-chart-scroll" aria-label="本步细流程">
        <div className="fc-chart">
          <Spine>{children}</Spine>
        </div>
      </div>
    </div>
  )
}

function StepDetail({
  step,
  cfg,
  enabled,
  isActiveForum,
  board,
}: {
  step: TopoStepId
  cfg: ForumCrawlerConfig
  enabled: boolean
  isActiveForum: boolean
  board?: ForumBoard
}) {
  const pages = cfg.web_crawler_list_pages_per_board || 15
  const delay = cfg.web_crawler_request_delay
  const failN = cfg.web_crawler_fetch_failure_threshold
  const cool = cfg.web_crawler_fetch_cooldown_seconds
  const target = cfg.web_crawler_target_imports
  const linkKind = board?.primary_link === 'ed2k' ? '电驴优先' : '磁力优先'
  const boardRule =
    board?.fid === '95'
      ? '仅分类 716 · 发帖时间序'
      : board?.fid === '141'
        ? '未满 3 天不入队 · 发帖时间序'
        : '发帖时间序列表'
  const enabledCount = cfg.enabled_board_fids?.length || (cfg.active_board_fid ? 1 : 0)
  const enabledLabel = enabledCount > 0 ? ` · 启用 ${enabledCount} 板` : ''
  const headPages =
    (board?.fid && cfg.board_manual_head_pages?.[board.fid]) ||
    cfg.web_crawler_manual_head_pages ||
    20
  const knownStop = cfg.web_crawler_list_known_stop_pages || 2
  const maxCool = cfg.web_crawler_fetch_max_cooldowns || 3
  const prefer = board?.primary_link === 'ed2k' ? '电驴' : '磁力'

  if (step === 'switch') {
    return (
      <ChartShell hint="连续深扫受总开关约束。手动立即/扫新帖、随机连续、账号重爬、异常重试不要求开关开，但与 looping/running 互斥。停止后若 running+停止标卡住，手动入口会先复位再跑。队列行永不因停止而删除。">
        <Process text="读爬虫开关" sub={`当前：${cfg.web_crawler_enabled ? '开' : '关'}`} />
        <ArrowDown />
        <Decision text="触发来源？" />
        <ArrowDown />
        <Junction cols={4}>
          <Branch label="连续深扫">
            <Spine>
              <Decision text="开关开且为本论坛？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="否">
                  <Terminal text="循环待命" sub="约 5s 轮询 · 不退出 loop" kind="muted" />
                </Branch>
                <Branch label="是" main>
                  <Terminal
                    text="进入调度"
                    sub={isActiveForum && enabled ? '当前满足 · loop=deep' : '需启用本论坛'}
                    kind="ok"
                  />
                </Branch>
              </Junction>
            </Spine>
          </Branch>
          <Branch label="手动立即 / 扫新帖" main>
            <Spine>
              <Process text="复位卡住状态" sub="running+停止标 → idle · 清 stop" />
              <ArrowDown />
              <Terminal text="可直接开跑" sub="不要求开关 · 真忙才 409" kind="ok" />
            </Spine>
          </Branch>
          <Branch label="侧线任务">
            <Spine>
              <Terminal text="随机抓帖连续" sub="loop=random_tid · 与深扫互斥" kind="ok" />
              <ArrowDown sm />
              <Terminal text="账号重爬" sub="失败/无权跳过 → 占位 · 需账号 Cookie" kind="warn" />
              <ArrowDown sm />
              <Terminal text="异常重试" sub="只吃异常队列 · 不扫列表" kind="warn" />
            </Spine>
          </Branch>
          <Branch label="停止 / 备份">
            <Spine>
              <Terminal text="手动/紧急停止" sub="cancel 任务 · 强制 idle · 队列保留" kind="fail" />
              <ArrowDown sm />
              <Terminal text="资源库备份" sub="先停爬 · 备完按原 loop 恢复" kind="muted" />
            </Spine>
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  if (step === 'scheduler') {
    return (
      <ChartShell hint="深扫连续：一轮结束仅 sleep(0.05) 让出事件循环，无分钟级轮间间隔。连续路径只做深扫（scan_head=False），不跑每日捕新。">
        <Process text="连续执行" sub="无轮间间隔 · loop_kind=deep" />
        <ArrowDown />
        <Process
          text="套用请求节奏"
          sub={`延迟 ${delay} 秒 · 节流窗口 ${cfg.web_crawler_autothrottle_window} · 上限 ${cfg.web_crawler_autothrottle_max_delay}s`}
        />
        <ArrowDown />
        <Decision text="本轮列表模式？" />
        <ArrowDown />
        <Junction cols={3}>
          <Branch label="连续 / 立即">
            <Terminal text="仅深扫" sub="跳过首页捕新 · 游标续扫" kind="ok" />
          </Branch>
          <Branch label="扫新帖按钮" main>
            <Terminal text="多板捕新" sub="每板 head 后同锁抓帖 · 再收尾消化" kind="ok" />
          </Branch>
          <Branch label="异常重试">
            <Terminal text="不扫列表" sub="queue_kind=abnormal" kind="warn" />
          </Branch>
        </Junction>
        <ArrowDown />
        <Terminal
          text="进入选板"
          sub={
            target > 0
              ? `抓帖环：入库+占位目标 ${target} · 失败阈值 ${failN}/${cool}s`
              : `抓帖环：失败阈值 ${failN} · 冷却 ${cool}s`
          }
          kind="ok"
        />
      </ChartShell>
    )
  }

  if (step === 'board_select') {
    return (
      <ChartShell hint="启用板按 board_order。一轮内：先列表（当前板）→ 再抓帖（启用板合计队列）。深扫触底后于抓帖结束再切 active_board_fid；扫新帖则逐板捕新。">
        <Process
          text="读取启用队列"
          sub={
            board
              ? `当前 ${board.name}（${board.key || board.fid}）${enabledLabel}`
              : `未选择${enabledLabel}`
          }
        />
        <ArrowDown />
        <Decision text="在白名单 BOARD_POLICIES？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="否">
            <Terminal text="拒绝" sub="不可爬未登记板块" kind="fail" />
          </Branch>
          <Branch label="是" main>
            <Spine>
              <Process text="加载板块策略" sub={`${linkKind} · ${boardRule}`} />
              <ArrowDown />
              <Decision text="深扫本轮列表触底？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="是 · list_exhausted">
                  <Terminal text="抓帖后再切下一板" sub="游标保留在板底 · 不中途换板" kind="ok" />
                </Branch>
                <Branch label="否" main>
                  <Terminal text="进入进站" sub="先建/复用浏览器会话" kind="ok" />
                </Branch>
              </Junction>
            </Spine>
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  if (step === 'session') {
    return (
      <ChartShell hint="混合取页：浏览器过十八禁门并同步 Cookie；列表用浏览器读；帖子优先指纹 HTTP + Cookie，软文壳可整页浏览器重读。">
        <Process text="启动浏览器" sub="预置安全浏览标记 · 加载已存凭据" />
        <ArrowDown />
        <Process text="打开首页 / 过十八禁门" sub="点进入 · 处理安全浏览壳" />
        <ArrowDown />
        <Process text="探测列表页" sub="确认论坛正常页" />
        <ArrowDown />
        <Process text="同步 Cookie 落盘" sub="供后续 HTTP 读帖使用" />
        <ArrowDown />
        <Terminal text="会话就绪" sub="列表→浏览器 · 帖子→HTTP（可升浏览器）" kind="ok" />
      </ChartShell>
    )
  }

  if (step === 'list_scan') {
    return (
      <ChartShell
        hint={`顺序：列表 → 抓帖。背压：启用板 ready≥150 则跳过列表只消化队列。深扫每轮 ${pages} 页游标续扫；扫新帖每板≤${headPages} 页，连续 ${knownStop} 页「全已知」早停（未满龄跳过页不计已知）。`}
      >
        <Decision text="启用子板 ready 合计 ≥ 150？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="是 · 背压">
            <Terminal text="跳过列表入队" sub="仍抓启用板待抓 · 异常不计入背压" kind="warn" />
          </Branch>
          <Branch label="否" main>
            <Spine>
              <Process
                text="拼列表地址"
                sub={
                  board?.fid === '95'
                    ? '分类 716 · 按发帖时间排序'
                    : '按发帖时间排序 · 第 n 页'
                }
              />
              <ArrowDown />
              <Decision text="本轮是手动扫新帖？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="是 · 捕新">
                  <Spine>
                    <Process
                      text="自第 1 页捕新"
                      sub={`上限 ${headPages} 页 · 可板级覆盖 · 不写每日捕新闸`}
                    />
                    <ArrowDown />
                    <Process text="浏览器读列表 · 解析帖链" sub="跳过置顶 · 发帖时间序" />
                    <ArrowDown />
                    <Decision text={`连续 ${knownStop} 页均已入库？`} />
                    <ArrowDown />
                    <Junction cols={3}>
                      <Branch label="是 · 完成">
                        <Terminal text="本板捕新结束" sub="同锁抓帖 → 下一启用板" kind="muted" />
                      </Branch>
                      <Branch label="触达上限仍有新">
                        <Terminal text="记未完成" sub="可再点扫新帖续扫" kind="warn" />
                      </Branch>
                      <Branch label="有新帖" main>
                        <Terminal text="写入待抓队列" sub="已有资源只改二级板块名" kind="ok" />
                      </Branch>
                    </Junction>
                  </Spine>
                </Branch>
                <Branch label="否 · 深扫" main>
                  <Spine>
                    <Process
                      text="浏览器打开列表"
                      sub={`自游标向更旧 · 本轮 ${pages} 页 · 缺失才入队`}
                    />
                    <ArrowDown />
                    <Decision text="网页内容是否正常？" />
                    <ArrowDown />
                    <Junction cols={3}>
                      <Branch label="仍卡十八禁/壳">
                        <Terminal text="记失败" sub="强制重进站后再试" kind="warn" />
                      </Branch>
                      <Branch label="需登录">
                        <Terminal text="停本板列表" sub="补登录凭据 · 仍可抓已有队列" kind="warn" />
                      </Branch>
                      <Branch label="正常论坛页" main>
                        <Spine>
                          <Process
                            text="解析帖链并入队"
                            sub={
                              board?.fid === '141'
                                ? '跳过置顶 · 未满 3 天永不入队'
                                : '跳过置顶 · 按发帖时间序'
                            }
                          />
                          <ArrowDown />
                          <Decision text="本轮列表状态？" />
                          <ArrowDown />
                          <Junction cols={3}>
                            <Branch label="空页 / 夹页 / 回首页">
                              <Terminal text="list_exhausted" sub="抓帖后切下一启用板" kind="muted" />
                            </Branch>
                            <Branch label="本轮配额已满">
                              <Terminal text="同板续扫" sub={`游标保留 · 下轮再扫 ${pages} 页`} kind="ok" />
                            </Branch>
                            <Branch label="页内有新帖" main>
                              <Terminal text="写入待抓队列" sub="进入抓帖环" kind="ok" />
                            </Branch>
                          </Junction>
                        </Spine>
                      </Branch>
                    </Junction>
                  </Spine>
                </Branch>
              </Junction>
            </Spine>
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  if (step === 'thread_crawl') {
    return (
      <ChartShell hint="主链路：取启用板合计待抓 → HTTP 读帖 → 按页回写二级板块 → 判定/附件/双链解析（仅一楼）→ 回写队列。软文壳并入异常队列（无独立 soft_ad）。侧线见后两步。">
        <Process text="取待抓队列" sub="启用子板合计 · ready + 已到期异常" />
        <ArrowDown />
        <Decision text="本轮来源？" />
        <ArrowDown />
        <Junction cols={2}>
          <Branch label="异常专重试">
            <Terminal text="只取异常队列" sub="忽略退避 · 成功才出队 · 不扫列表" kind="warn" />
          </Branch>
          <Branch label="正常抓帖" main>
            <Terminal text="ready + 到期异常" sub="列表已扫或背压跳过后再抓" kind="ok" />
          </Branch>
        </Junction>
        <ArrowDown />
        <Process text="HTTP 读取帖页" sub="会话 Cookie · 软文壳可升浏览器整页重读" />
        <ArrowDown />
        <Process text="解析真实板块" sub="fid + typeid → 如 142:706 转帖·合集" />
        <ArrowDown />
        <Decision text="页面是否软文/安全壳？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="是">
            <Spine>
              <Process text="浏览器整页重读" sub="同会话 · 至多一次" />
              <ArrowDown />
              <Decision text="重读后仍是壳？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="是">
                  <Terminal text="保留重试" sub="异常队列 · 退避约 3600s · 最多 3 次" kind="warn" />
                </Branch>
                <Branch label="否" main>
                  <Terminal text="回到正文判定" kind="ok" />
                </Branch>
              </Junction>
            </Spine>
          </Branch>
          <Branch label="否" main>
            <Spine>
              <Decision text="需登录 / 无阅读权限？" />
              <ArrowDown />
              <Junction cols={3}>
                <Branch label="需登录·有标题">
                  <Terminal text="占位入库" sub="帖子需论坛登录" kind="warn" />
                </Branch>
                <Branch label="无权限">
                  <Terminal text="占位入库" sub="页内标题或列表标题" kind="warn" />
                </Branch>
                <Branch label="正常 / 无标题登录" main>
                  <Spine>
                    <Decision text="龄期板未满龄？（如 141）" />
                    <ArrowDown />
                    <Junction pair>
                      <Branch label="未满龄">
                        <Terminal text="跳过" sub="不占位 · 列表阶段已拦" kind="muted" />
                      </Branch>
                      <Branch label="已满龄 / 非龄期板" main>
                        <Spine>
                          <Decision text="115sha / 纯网盘标题？" />
                          <ArrowDown />
                          <Junction pair>
                            <Branch label="是">
                              <Terminal text="跳过" sub="非目标链 · 立即出队" kind="muted" />
                            </Branch>
                            <Branch label="否" main>
                              <Spine>
                                <Decision text="需回复 / 需购买？" />
                                <ArrowDown />
                                <Junction cols={3}>
                                  <Branch label="需回复">
                                    <Terminal text="占位入库" sub="需回复贴" kind="warn" />
                                  </Branch>
                                  <Branch label="需购买">
                                    <Terminal text="占位入库" sub="需购买贴" kind="warn" />
                                  </Branch>
                                  <Branch label="否" main>
                                    <Spine>
                                      <Process
                                        text="一楼语料 + 双链解析"
                                        sub={`magnet/ed2k/115 · 主链偏好 ${prefer} · 裸 hash：特征/验证/种子特码…`}
                                      />
                                      <ArrowDown />
                                      <Decision text="正文已有目标链接？" />
                                      <ArrowDown />
                                      <Junction pair>
                                        <Branch label="有" main>
                                          <Spine>
                                            <Decision text="解析出主资源？" />
                                            <ArrowDown />
                                            <Junction pair>
                                              <Branch label="是" main>
                                                <Terminal text="进入入库" sub="可 ×N 多子资源" kind="ok" />
                                              </Branch>
                                              <Branch label="否">
                                                <Terminal text="失败出队" sub="有链形态无主资源" kind="fail" />
                                              </Branch>
                                            </Junction>
                                          </Spine>
                                        </Branch>
                                        <Branch label="无">
                                          <Spine>
                                            <Process
                                              text="附件策略"
                                              sub="torrent↔磁力 / txt·压缩包电驴 · 双向回退"
                                            />
                                            <ArrowDown />
                                            <Decision text="附件结果？" />
                                            <ArrowDown />
                                            <Junction cols={3}>
                                              <Branch label="含 115sha">
                                                <Terminal text="跳过" sub="立即出队" kind="muted" />
                                              </Branch>
                                              <Branch label="解析出目标链" main>
                                                <Terminal text="进入入库" sub="正文+附件合并" kind="ok" />
                                              </Branch>
                                              <Branch label="未出链">
                                                <Spine>
                                                  <Decision text="仍无目标链？" />
                                                  <ArrowDown />
                                                  <Junction pair>
                                                    <Branch label="无权限下载">
                                                      <Terminal text="占位入库" sub="无权限下载附件" kind="warn" />
                                                    </Branch>
                                                    <Branch label="其它" main>
                                                      <Terminal
                                                        text="保留重试"
                                                        sub="附件约 600s / 其它约 900s · 最多 3 次→失败"
                                                        kind="warn"
                                                      />
                                                    </Branch>
                                                  </Junction>
                                                </Spine>
                                              </Branch>
                                            </Junction>
                                          </Spine>
                                        </Branch>
                                      </Junction>
                                    </Spine>
                                  </Branch>
                                </Junction>
                              </Spine>
                            </Branch>
                          </Junction>
                        </Spine>
                      </Branch>
                    </Junction>
                  </Spine>
                </Branch>
              </Junction>
            </Spine>
          </Branch>
        </Junction>
        <ArrowDown />
        <Process text="回写队列状态" sub="入库/占位出队 · 跳过结束 · 重试挂起 · 满 3 次→失败丢弃" />
        <ArrowDown />
        {target > 0 ? (
          <>
            <Decision text={`本批入库+占位 ≥ ${target}？`} />
            <ArrowDown />
            <Junction pair>
              <Branch label="已达上限">
                <Terminal text="本批收工" sub="本轮抓帖环结束" kind="muted" />
              </Branch>
              <Branch label="未达" main>
                <Spine>
                  <Decision text={`连续失败 ≥ ${failN}？`} />
                  <ArrowDown />
                  <Junction pair>
                    <Branch label="是">
                      <Terminal text="冷却后再抓" sub={`${cool} 秒 · 最多 ${maxCool} 次熔断`} kind="warn" />
                    </Branch>
                    <Branch label="否" main>
                      <Terminal text="继续下一帖" sub={`请求间隔 ${delay} 秒`} kind="ok" />
                    </Branch>
                  </Junction>
                </Spine>
              </Branch>
            </Junction>
          </>
        ) : (
          <>
            <Decision text={`连续失败 ≥ ${failN}？`} />
            <ArrowDown />
            <Junction pair>
              <Branch label="是">
                <Terminal text="冷却后再抓" sub={`${cool} 秒 · 最多 ${maxCool} 次熔断`} kind="warn" />
              </Branch>
              <Branch label="否" main>
                <Terminal text="继续下一帖" sub={`请求间隔 ${delay} 秒`} kind="ok" />
              </Branch>
            </Junction>
          </>
        )}
      </ChartShell>
    )
  }

  if (step === 'import') {
    return (
      <ChartShell hint="正常写主资源（同帖多链可 ×N 合集）；占位写无链占位；失败不写；跳过可清坏占位；重试不入库。真链入库会删旧占位。">
        <Process text="接收抓帖判定" sub="import / stub / skipped / failed / retry" />
        <ArrowDown />
        <Decision text="判定结果？" />
        <ArrowDown />
        <Junction cols={3}>
          <Branch label="正常入库" main>
            <Spine>
              <Process text="写入/更新资源" sub="按帖聚合 · 多子资源 ×N · 预览按 hash 绑定" />
              <ArrowDown />
              <Terminal text="成功" sub="处理记录可见 · 可清旧 stub" kind="ok" />
            </Spine>
          </Branch>
          <Branch label="占位入库">
            <Spine>
              <Process text="写入占位帖" sub="unavailable://thread/…" />
              <ArrowDown />
              <Terminal text="占位完成" sub="登录/回复/购买/附件无权" kind="warn" />
            </Spine>
          </Branch>
          <Branch label="跳过 / 失败 / 重试">
            <Spine>
              <Terminal
                text="不写或清理"
                sub="跳过·可删坏占位 · 失败·丢弃 · 重试·挂起"
                kind="muted"
              />
            </Spine>
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  if (step === 'random_tid') {
    return (
      <ChartShell hint="活动页「随机抓帖」= 连续循环（loop_kind=random_tid），与深扫连续互斥；不写待抓队列；停止后清空本会话已探 tid。">
        <Process text="启动随机连续调度" sub="清 stop · 清空本会话抽样" />
        <ArrowDown />
        <Process text="每轮随机探测" sub="默认 200 个 tid · 范围可配 · 跳过已入库/已在队列" />
        <ArrowDown />
        <Process text="直链读帖判定" sub="preferred=both · 一楼双链 + 裸 hash 规则" />
        <ArrowDown />
        <Decision text="本轮探测跑满？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="是">
            <Terminal text="无间隔开下一轮" sub="仅 sleep(0.05) 让出" kind="ok" />
          </Branch>
          <Branch label="手动停止">
            <Terminal text="退出循环" sub="清空会话已探 · 下次重抽" kind="fail" />
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  // account_stub
  return (
    <ChartShell hint="「账号重爬」：① 未处理失败 ② 无阅读权限跳过 ③ 库内优先占位。需账号 Cookie；与 looping/running 互斥。登录后变成需回复/需购买则跳过并删占位。">
      <Process text="校验账号 Cookie" sub="未配置则拒绝 · 与游客 Cookie 分开" />
      <ArrowDown />
      <Process text="① 未处理：失败" sub="discarded failed · 账号 Cookie 抓帖" />
      <ArrowDown />
      <Process text="② 未处理：无阅读权限跳过" sub="access_denied_bad_title" />
      <ArrowDown />
      <Process text="③ 查库优先占位" sub="需登录 / 无权 / 附件无权 · remaining 每次重算" />
      <ArrowDown />
      <Decision text="还有未尝试项？" />
      <ArrowDown />
      <Junction pair>
        <Branch label="无">
          <Terminal text="本轮结束" sub="进度：已处理 / 升级 / 仍占位 / 失败" kind="muted" />
        </Branch>
        <Branch label="有" main>
          <Spine>
            <Process text="账号会话抓帖" sub="cookie_override · 独立 jar" />
            <ArrowDown />
            <Decision text="结果？" />
            <ArrowDown />
            <Junction cols={3}>
              <Branch label="import">
                <Terminal text="删旧占位 · 正常入库" sub="stub hash ≠ 真链 hash" kind="ok" />
              </Branch>
              <Branch label="仍 stub">
                <Terminal text="保留占位" sub="本轮不再重试该 hash" kind="warn" />
              </Branch>
              <Branch label="需回复/购买/失败">
                <Terminal text="跳过或记失败" sub="回复/购买→删占位出队" kind="fail" />
              </Branch>
            </Junction>
            <ArrowDown />
            <Terminal text="取下一条" sub="不限数量 · 可手动停止" kind="ok" />
          </Spine>
        </Branch>
      </Junction>
    </ChartShell>
  )
}

function buildPipeline(
  forum: ForumItem & { crawler_config: ForumCrawlerConfig },
  activeForumId: string,
  boards: ForumBoard[],
  activeBoardFid: string,
): PipelineNode[] {
  const cfg = forum.crawler_config
  const enabled = !!cfg.web_crawler_enabled && activeForumId === forum.id
  const board = boards.find((b) => (b.key || (b.typeid ? `${b.fid}:${b.typeid}` : b.fid)) === activeBoardFid)
  const pages = cfg.web_crawler_list_pages_per_board || 15
  const headPages =
    (activeBoardFid && cfg.board_manual_head_pages?.[activeBoardFid]) ||
    cfg.web_crawler_manual_head_pages ||
    20
  return [
    {
      id: 'switch',
      label: '开关',
      detail: enabled ? '已启用' : '已关闭',
      status: enabled ? 'active' : 'idle',
    },
    {
      id: 'scheduler',
      label: '调度',
      detail: enabled
        ? `连续无间隔 · 延迟 ${cfg.web_crawler_request_delay} 秒`
        : '深扫连续 / 手动模式',
      status: enabled ? 'active' : 'idle',
    },
    {
      id: 'board_select',
      label: '选板',
      detail: (() => {
        const n = cfg.enabled_board_fids?.length || (board ? 1 : 0)
        if (!board && !n) return '未选择'
        return board ? `${board.name} · 启用 ${n} 板` : `启用 ${n} 板`
      })(),
      status: enabled ? 'ready' : 'idle',
    },
    {
      id: 'session',
      label: '进站',
      detail: '浏览器过门 · Cookie 同步',
      status: enabled ? 'ready' : 'idle',
    },
    {
      id: 'list_scan',
      label: '扫列表',
      detail: `背压≥150 · 深扫 ${pages} 页 · 扫新帖 ≤${headPages}`,
      status: 'idle',
    },
    {
      id: 'thread_crawl',
      label: '抓帖',
      detail: '一楼双链 · 异常队列 · 目标/冷却',
      status: 'idle',
    },
    {
      id: 'import',
      label: '入库',
      detail: '×N 合集 · 占位 · 跳过可清',
      status: 'idle',
    },
    {
      id: 'random_tid',
      label: '随机',
      detail: '连续 200/轮 · 不进队列',
      status: 'idle',
    },
    {
      id: 'account_stub',
      label: '账号重爬',
      detail: '失败→无权→占位',
      status: 'idle',
    },
  ]
}

const STEP_TITLE: Record<TopoStepId, string> = {
  switch: '① 开关 — 细步骤',
  scheduler: '② 调度 — 细步骤',
  board_select: '③ 选板 — 细步骤',
  session: '④ 进站 — 细步骤',
  list_scan: '⑤ 扫列表 — 细步骤',
  thread_crawl: '⑥ 抓帖 — 细步骤',
  import: '⑦ 入库 — 细步骤',
  random_tid: '⑧ 随机抓帖 — 侧线',
  account_stub: '⑨ 账号重爬 — 侧线',
}

export function ForumTopology({ forum, activeForumId, boards, activeBoardFid }: Props) {
  const [params, setParams] = useSearchParams()
  const step = parseStep(params.get('step'))
  const cfg = forum.crawler_config
  const enabled = !!cfg.web_crawler_enabled && activeForumId === forum.id
  const isActiveForum = activeForumId === forum.id
  const board = boards.find((b) => (b.key || (b.typeid ? `${b.fid}:${b.typeid}` : b.fid)) === activeBoardFid)
  const enabledCount = cfg.enabled_board_fids?.length || (activeBoardFid ? 1 : 0)
  const nodes = useMemo(
    () => buildPipeline(forum, activeForumId, boards, activeBoardFid),
    [forum, activeForumId, boards, activeBoardFid],
  )

  const setStep = (next: TopoStepId) => {
    setParams(
      (prev) => {
        const out = new URLSearchParams(prev)
        out.set('tab', 'forums')
        out.set('forum', forum.id)
        out.set('panel', 'topology')
        out.set('step', next)
        return out
      },
      { replace: true },
    )
  }

  return (
    <div className="forum-tab-content crawl-topology">
      <div className="crawl-topo-head">
        <div className="crawl-topo-head-main">
          {enabled ? <span className="tag tag-pending">待命</span> : <span className="tag tag-disabled">已关闭</span>}
          <span className="crawl-topo-summary">
            主链路：列表→抓帖（背压可跳列表）· 连续深扫无轮间间隔 · 触底后切板 · 启用 {enabledCount}{' '}
            板；侧线：随机连续 / 账号重爬 / 异常重试；停止保留队列并可复位卡住状态
          </span>
          {board ? <span className="crawl-topo-current">深扫当前 · {board.name}</span> : null}
        </div>
      </div>

      <div className="crawl-topo-section">
        <div className="crawl-topo-section-title">总览流程</div>
        <p className="hint crawl-topo-pipeline-hint">点击下方节点，查看该步细流程（一步一页）</p>
        <div className="fc-hflow" aria-label="总览流程" role="tablist">
          {nodes.map((node, idx) => (
            <Fragment key={node.id}>
              <button
                type="button"
                role="tab"
                aria-selected={step === node.id}
                className={`fc-hnode fc-hnode--${node.status}${step === node.id ? ' fc-hnode--selected' : ''}`}
                title={node.detail}
                onClick={() => setStep(node.id)}
              >
                <span className="fc-text">{node.label}</span>
                {node.detail ? <span className="fc-sub">{node.detail}</span> : null}
              </button>
              {idx < nodes.length - 1 ? <ArrowRight /> : null}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="crawl-topo-section crawl-topo-section--flowchart">
        <div className="crawl-topo-section-title">{STEP_TITLE[step]}</div>
        <StepDetail
          step={step}
          cfg={cfg}
          enabled={enabled}
          isActiveForum={isActiveForum}
          board={board}
        />
      </div>
    </div>
  )
}
