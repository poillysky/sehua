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
  const linkKind = board?.primary_link === 'ed2k' ? '电驴' : '磁力'
  const boardRule =
    board?.fid === '95'
      ? '仅分类 716 · 发帖时间序'
      : board?.fid === '141'
        ? '满 3 天才入队 · 发帖时间序'
        : '发帖时间序列表'
  const enabledCount = cfg.enabled_board_fids?.length || (cfg.active_board_fid ? 1 : 0)
  const enabledLabel = enabledCount > 0 ? ` · 启用 ${enabledCount} 板` : ''

  if (step === 'switch') {
    return (
      <ChartShell hint="连续深扫受总开关约束。手动立即/扫新帖、随机连续、账号爬占位、异常重试不要求开关开，但与 looping/running 互斥。手动停止/关开关：协作退出并保留队列。资源库备份会先停爬虫，完成后按原 loop 恢复。">
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
                  <Terminal text="不调度" sub="关时循环 5s 待命" kind="muted" />
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
            <Terminal
              text="可直接开跑"
              sub="不要求开关 · busy 时拒绝"
              kind="ok"
            />
          </Branch>
          <Branch label="侧线任务">
            <Spine>
              <Terminal text="随机抓帖连续" sub="loop=random_tid · 与深扫互斥" kind="ok" />
              <ArrowDown sm />
              <Terminal text="账号爬占位" sub="需账号 Cookie · 不进待抓队列" kind="warn" />
              <ArrowDown sm />
              <Terminal text="异常重试" sub="只吃异常队列 · 不扫列表" kind="warn" />
            </Spine>
          </Branch>
          <Branch label="停止 / 备份">
            <Spine>
              <Terminal text="手动停止" sub="关开关 · 队列保留" kind="fail" />
              <ArrowDown sm />
              <Terminal text="资源库备份" sub="先停爬 · 备完再按原 loop 开" kind="muted" />
            </Spine>
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  if (step === 'scheduler') {
    return (
      <ChartShell hint="深扫连续：一轮结束几乎无间隔再开。开关关时循环不退出，约 5s 轮询待命。入库上限与失败冷却在「抓帖」环内判定。">
        <Process text="连续执行" sub="无轮间间隔 · loop_kind=deep" />
        <ArrowDown />
        <Process
          text="套用请求节奏"
          sub={`延迟 ${delay} 秒 · 节流窗口 ${cfg.web_crawler_autothrottle_window} · 上限 ${cfg.web_crawler_autothrottle_max_delay}s`}
        />
        <ArrowDown />
        <Process
          text="本轮列表模式"
          sub="连续/立即 → 仅深扫；扫新帖按钮 → 多板捕新（每板扫完即抓帖）"
        />
        <ArrowDown />
        <Terminal
          text="进入选板"
          sub={
            target > 0
              ? `抓帖环内：入库+占位目标 ${target} · 失败阈值 ${failN}/${cool}s`
              : `抓帖环内：失败阈值 ${failN} · 冷却 ${cool}s`
          }
          kind="ok"
        />
      </ChartShell>
    )
  }

  if (step === 'board_select') {
    return (
      <ChartShell hint="多选启用板块按 board_order 依次爬；深扫扫完当前板后切下一板，扫新帖每板达标后换下一板">
        <Process
          text="读取启用队列"
          sub={
            board
              ? `当前 ${board.name}（${board.fid}）${enabledLabel}`
              : `未选择${enabledLabel}`
          }
        />
        <ArrowDown />
        <Decision text="在白名单？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="否">
            <Terminal text="拒绝" sub="不可爬未登记板块" kind="fail" />
          </Branch>
          <Branch label="是" main>
            <Spine>
              <Process text="加载板块策略" sub={`${linkKind} · ${boardRule}`} />
              <ArrowDown />
              <Decision text="策略就绪？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="否">
                  <Terminal text="跳过本轮" sub="补全配置后再跑" kind="warn" />
                </Branch>
                <Branch label="是" main>
                  <Terminal text="进入进站" sub="先建浏览器会话" kind="ok" />
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
      <ChartShell hint="混合取页：浏览器过十八禁门并同步 Cookie；列表用浏览器读；帖子用指纹 HTTP + Cookie 读">
        <Process text="启动浏览器" sub="预置安全浏览标记 · 加载已存凭据" />
        <ArrowDown />
        <Process text="打开首页 / 过十八禁门" sub="点进入 · 处理安全浏览壳" />
        <ArrowDown />
        <Process text="探测列表页" sub="确认论坛正常页" />
        <ArrowDown />
        <Process text="同步 Cookie 落盘" sub="供后续 HTTP 读帖使用" />
        <ArrowDown />
        <Terminal text="会话就绪" sub="列表→浏览器 · 帖子→HTTP" kind="ok" />
      </ChartShell>
    )
  }

  if (step === 'list_scan') {
    const headPages =
      (board?.fid && cfg.board_manual_head_pages?.[board.fid]) ||
      cfg.web_crawler_manual_head_pages ||
      20
    const knownStop = cfg.web_crawler_list_known_stop_pages || 2
    return (
      <ChartShell hint={`扫列表前先看队列背压；连续/立即：每轮深扫 ${pages} 页至板底（已知资源只改二级板块名，缺失才抓帖）；扫新帖：每板上限 ${headPages} 页（可板级覆盖），连续 ${knownStop} 页全已知早停，且本板扫完后同轮进入抓帖`}>
        <Decision text="启用子板正常待抓合计 ≥ 150？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="是 · 背压">
            <Terminal text="跳过列表入队" sub="按启用合计取待抓消化 · 异常/软文不计背压" kind="warn" />
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
                      text="自进度页捕新"
                      sub={`上限 ${headPages} 页 · 多板按序 · 不写每日捕新闸门`}
                    />
                    <ArrowDown />
                    <Process text="浏览器读列表 · 解析帖链" sub="跳过置顶 · 发帖时间序" />
                    <ArrowDown />
                    <Decision text={`连续 ${knownStop} 页均已入库？`} />
                    <ArrowDown />
                    <Junction cols={3}>
                      <Branch label="是 · 完成">
                        <Terminal text="本板捕新结束" sub="同轮抓帖后切下一板" kind="muted" />
                      </Branch>
                      <Branch label="触达上限仍有新">
                        <Terminal text="下轮续扫" sub="保留 head 进度页" kind="warn" />
                      </Branch>
                      <Branch label="有新帖" main>
                        <Terminal text="写入待抓队列" sub="持久队列 · 同轮抓帖" kind="ok" />
                      </Branch>
                    </Junction>
                  </Spine>
                </Branch>
                <Branch label="否 · 深扫" main>
                  <Spine>
                    <Process text="浏览器打开列表" sub={`自游标向更旧推进 · 本轮 ${pages} 页 · 已有只改板块 · 缺失才入队`} />
                    <ArrowDown />
                    <Decision text="网页内容是否正常？" />
                    <ArrowDown />
                    <Junction cols={3}>
                      <Branch label="仍卡十八禁/壳">
                        <Terminal text="记失败" sub="强制重进站后再试" kind="warn" />
                      </Branch>
                      <Branch label="需登录">
                        <Terminal text="停板" sub="补登录凭据" kind="warn" />
                      </Branch>
                      <Branch label="正常论坛页" main>
                        <Spine>
                          <Process
                            text="解析帖链并入队"
                            sub={
                              board?.fid === '141'
                                ? '跳过置顶 · 仅入队发帖已满 3 天'
                                : '跳过置顶 · 按发帖时间序'
                            }
                          />
                          <ArrowDown />
                          <Decision text="本轮状态？" />
                          <ArrowDown />
                          <Junction cols={3}>
                            <Branch label="空页 / 夹页 · 板底">
                              <Terminal text="切下一启用板" sub="到底切板 · 游标保留" kind="muted" />
                            </Branch>
                            <Branch label="本轮配额已满">
                              <Terminal text="同板续扫" sub={`游标保留 · 下轮再扫 ${pages} 页`} kind="ok" />
                            </Branch>
                            <Branch label="页内有新帖" main>
                              <Terminal text="写入待抓队列" sub="进入抓帖" kind="ok" />
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
    const prefer = board?.primary_link === 'ed2k' ? '电驴' : '磁力'
    const maxCool = cfg.web_crawler_fetch_max_cooldowns || 3
    const attachHint =
      board?.primary_link === 'ed2k'
        ? '正文无电驴 → 下尾部 txt/压缩包（需回复贴则不下）'
        : '正文无磁力 → 下 .torrent 转磁力'
    return (
      <ChartShell hint="主链路抓帖：取待抓队列 → 单帖判定 → 回写 → 检查入库+占位目标/失败冷却。「随机抓帖」「账号爬占位」是独立侧线，见总览后两步。">
        <Process text="取待抓队列" sub="启用子板合计 · 正常 ready + 已到期异常" />
        <ArrowDown />
        <Decision text="本轮来源？" />
        <ArrowDown />
        <Junction cols={2}>
          <Branch label="异常专重试">
            <Terminal text="只取异常队列" sub="启用子板合计 · 忽略退避 · 成功才出队 · 不扫列表" kind="warn" />
          </Branch>
          <Branch label="正常抓帖" main>
            <Terminal text="正常+到期异常" sub="列表已扫或背压跳过后再抓" kind="ok" />
          </Branch>
        </Junction>
        <ArrowDown />
        <Process text="HTTP 读取帖页" sub="会话内请求 · 附带进站 Cookie（游客/年龄门）" />
        <ArrowDown />
        <Decision text="页面是否软文/安全壳？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="是">
            <Spine>
              <Process text="浏览器整页重读" sub="Playwright 导航帖址 · 同会话 Cookie" />
              <ArrowDown />
              <Decision text="重读后仍是软文/壳？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="是">
                  <Terminal text="保留重试" sub="异常队列 · 退避约 3600s · 最多 3 次" kind="warn" />
                </Branch>
                <Branch label="否" main>
                  <Terminal text="回到正文判定" sub="按正常帖继续分流" kind="ok" />
                </Branch>
              </Junction>
            </Spine>
          </Branch>
          <Branch label="否" main>
            <Spine>
              <Decision text="需登录？" />
              <ArrowDown />
              <Junction cols={3}>
                <Branch label="需登录·有标题">
                  <Terminal text="占位入库" sub="帖子需论坛登录" kind="warn" />
                </Branch>
                <Branch label="需登录·无标题">
                  <Terminal text="跳过" sub="无法识别帖名" kind="muted" />
                </Branch>
                <Branch label="否" main>
                  <Spine>
                    <Decision text="无阅读权限？" />
                    <ArrowDown />
                    <Junction cols={3}>
                      <Branch label="无权限·页内真标题">
                        <Terminal text="占位入库" sub="页内能读到正常标题才占位" kind="warn" />
                      </Branch>
                      <Branch label="无权限·提示信息等">
                        <Terminal text="跳过" sub="伪标题直接 pass，不占位" kind="muted" />
                      </Branch>
                      <Branch label="正常正文" main>
                        <Spine>
                          <Decision text="龄期板未满龄？（如原创区 3 天）" />
                          <ArrowDown />
                          <Junction pair>
                            <Branch label="未满龄">
                              <Terminal text="跳过" sub="不占位 · 列表入队时也会拦" kind="muted" />
                            </Branch>
                            <Branch label="已满龄 / 非龄期板" main>
                              <Spine>
                                <Decision text="正文含 115sha 直链？" />
                                <ArrowDown />
                                <Junction pair>
                                  <Branch label="是">
                                    <Terminal text="跳过" sub="115://…|size|hash|hash · 立即出队" kind="muted" />
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
                                            <Process text="抽正文 + 双链解析" sub={`目标主链：${prefer}`} />
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
                                                      <Terminal text="进入入库" sub="正常候选" kind="ok" />
                                                    </Branch>
                                                    <Branch label="否">
                                                      <Terminal text="失败出队" sub="有链无主资源 · 不写库" kind="fail" />
                                                    </Branch>
                                                  </Junction>
                                                </Spine>
                                              </Branch>
                                              <Branch label="无">
                                                <Spine>
                                                  <Process text="附件策略" sub={attachHint} />
                                                  <ArrowDown />
                                                  <Decision text="附件结果？" />
                                                  <ArrowDown />
                                                  <Junction cols={3}>
                                                    <Branch label="含 115sha">
                                                      <Terminal text="跳过" sub="附件识别到亦立即出队" kind="muted" />
                                                    </Branch>
                                                    <Branch label="解析出目标链" main>
                                                      <Terminal text="进入入库" sub="正文+附件合并" kind="ok" />
                                                    </Branch>
                                                    <Branch label="未出目标链">
                                                      <Spine>
                                                        <Decision text="仍无目标链时？" />
                                                        <ArrowDown />
                                                        <Junction pair>
                                                          <Branch label="无权限下载">
                                                            <Terminal text="占位入库" sub="无权限下载附件" kind="warn" />
                                                          </Branch>
                                                          <Branch label="其它" main>
                                                            <Spine>
                                                              <Decision text="网盘/非资源？" />
                                                              <ArrowDown />
                                                              <Junction pair>
                                                                <Branch label="是">
                                                                  <Terminal text="跳过" sub="非目标板资源 · 不再爬" kind="muted" />
                                                                </Branch>
                                                                <Branch label="否" main>
                                                                  <Terminal
                                                                    text="保留重试"
                                                                    sub={
                                                                      board?.fid === '95'
                                                                        ? '异常队列 · 退避约 900s · 最多 3 次'
                                                                        : '异常队列 · 附件失败约 600s / 其它约 900s · 最多 3 次'
                                                                    }
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
                  </Spine>
                </Branch>
              </Junction>
            </Spine>
          </Branch>
        </Junction>
        <ArrowDown />
        <Process text="回写队列状态" sub="入库/占位出队 · 跳过结束 · 重试挂起 · 满 3 次→失败" />
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
      <ChartShell hint="入库出口：正常写主资源；占位写无链占位；失败不写；跳过可清坏占位；重试不入库。账号爬占位升级成功会删旧占位另见侧线。">
        <Process text="接收抓帖判定" sub="正常 / 占位 / 跳过 / 失败 / 重试" />
        <ArrowDown />
        <Decision text="判定结果？" />
        <ArrowDown />
        <Junction cols={3}>
          <Branch label="正常入库" main>
            <Spine>
              <Process text="写入/更新资源" sub="每帖 1 主资源 · 同类链进列表" />
              <ArrowDown />
              <Terminal text="成功" sub="处理记录可见" kind="ok" />
            </Spine>
          </Branch>
          <Branch label="占位入库">
            <Spine>
              <Process text="写入占位帖" sub="无链占位地址" />
              <ArrowDown />
              <Terminal text="占位完成" sub="登录/回复/购买/附件无权" kind="warn" />
            </Spine>
          </Branch>
          <Branch label="跳过 / 失败 / 重试">
            <Spine>
              <Terminal
                text="不写或清理"
                sub="跳过·可删坏占位 · 失败·有链无资产 · 重试·挂起"
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
      <ChartShell hint="活动页「随机抓帖」= 连续循环（POST /random-tid/loop/start），与深扫连续互斥；不要求总开关开，但 looping/running 时拒绝。">
        <Process text="启动随机连续调度" sub="loop_kind=random_tid · 清空本会话抽样" />
        <ArrowDown />
        <Process text="每轮随机探测" sub="默认 200 个 tid · 范围可配 · 跳过已入库/已在队列" />
        <ArrowDown />
        <Process text="直链读帖入库" sub="不进待抓队列 · magnet+ed2k 混合判定" />
        <ArrowDown />
        <Decision text="本轮探测跑满？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="是">
            <Terminal text="无间隔开下一轮" sub="连续循环不停" kind="ok" />
          </Branch>
          <Branch label="手动停止">
            <Terminal text="退出循环" sub="清空本会话已探 tid · 下次重抽" kind="fail" />
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  // account_stub
  return (
    <ChartShell hint="活动页「账号爬占位」后台跑完优先占位队列；不进待抓列表；与 looping/running 互斥；需论坛配置里的账号 Cookie。">
      <Process text="校验账号 Cookie" sub="未配置则拒绝 · 与游客 Cookie 分开" />
      <ArrowDown />
      <Process
        text="查库优先占位队列"
        sub="需登录 / 无阅读权限 / 无权限下载附件 · 登录后需回复/需购买跳过删占位 · remaining 每次重算"
      />
      <ArrowDown />
      <Decision text="还有未尝试的优先占位？" />
      <ArrowDown />
      <Junction pair>
        <Branch label="无">
          <Terminal text="本轮结束" sub="进度：已处理 / 库内剩余" kind="muted" />
        </Branch>
        <Branch label="有" main>
          <Spine>
            <Process text="账号会话抓帖" sub="cookie_override · 独立 cookie jar" />
            <ArrowDown />
            <Decision text="升级为真链？" />
            <ArrowDown />
            <Junction cols={3}>
              <Branch label="import">
                <Terminal text="删旧占位 · 正常入库" sub="stub hash ≠ 真链 hash" kind="ok" />
              </Branch>
              <Branch label="仍 stub">
                <Terminal text="保留占位" sub="本轮不再重试该 hash" kind="warn" />
              </Branch>
              <Branch label="失败/其它">
                <Terminal text="记失败" sub="本轮跳过该 hash" kind="fail" />
              </Branch>
            </Junction>
            <ArrowDown />
            <Terminal text="取下一条" sub="不限数量 · 可手动停止中断" kind="ok" />
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
        : '节奏 / 模式',
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
      detail: `启用合计背压≥150 · 深扫每轮 ${pages} 页 · 扫新帖 ≤${headPages}`,
      status: 'idle',
    },
    {
      id: 'thread_crawl',
      label: '抓帖',
      detail: '队列环 · 115sha · 目标/冷却',
      status: 'idle',
    },
    {
      id: 'import',
      label: '入库',
      detail: '正常·占位·跳过可清',
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
      label: '账号占位',
      detail: '库内优先占位 · 跑完为止',
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
  account_stub: '⑨ 账号爬占位 — 侧线',
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
            主链路：连续深扫 · 背压跳列表 · 抓帖环（目标/冷却）· 启用 {enabledCount}{' '}
            板；侧线：随机连续 / 账号爬占位 / 异常重试
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
