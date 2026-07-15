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

function Junction({ children, pair, cols }: { children: ReactNode; pair?: boolean; cols?: 2 | 3 }) {
  const colCls = pair || cols === 3 ? ' fc-split-grid--3' : cols === 2 ? ' fc-split-grid--2' : ''
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
        ? '满 3 天 · 发帖时间序'
        : '发帖时间序列表'

  if (step === 'switch') {
    return (
      <ChartShell hint="本站开关：论坛爬虫总开关 + 是否为当前启用论坛；关闭则整条链路不跑">
        <Process text="读爬虫开关" sub={`当前：${cfg.web_crawler_enabled ? '开' : '关'}`} />
        <ArrowDown />
        <Decision text="开关开启？" />
        <ArrowDown />
        <Junction pair>
          <Branch label="关">
            <Terminal text="不调度" sub="保持待命 / 空转" kind="muted" />
          </Branch>
          <Branch label="开" main>
            <Spine>
              <Decision text="是否当前启用论坛？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="否">
                  <Terminal text="跳过本论坛" sub="只跑启用的专用爬虫" kind="warn" />
                </Branch>
                <Branch label="是" main>
                  <Terminal
                    text="进入调度"
                    sub={isActiveForum && enabled ? '当前满足' : '需启用本论坛'}
                    kind="ok"
                  />
                </Branch>
              </Junction>
            </Spine>
          </Branch>
        </Junction>
      </ChartShell>
    )
  }

  if (step === 'scheduler') {
    const maxCool = cfg.web_crawler_fetch_max_cooldowns || 3
    const failGate = (
      <Spine>
        <Decision text={`连续失败 ≥ ${failN}？`} />
        <ArrowDown />
        <Junction pair>
          <Branch label="是">
            <Terminal text="进入冷却" sub={`${cool} 秒 · 最多 ${maxCool} 次`} kind="warn" />
          </Branch>
          <Branch label="否" main>
            <Terminal text="进入选板" sub="带限速进入下一步" kind="ok" />
          </Branch>
        </Junction>
      </Spine>
    )
    return (
      <ChartShell hint="本站连续调度：一轮结束立即再开，无轮间间隔；仅请求延迟与失败冷却限速（深扫页数在「扫列表」）">
        <Process text="连续执行" sub="无轮间间隔 · 循环不停" />
        <ArrowDown />
        <Process
          text="套用请求节奏"
          sub={`延迟 ${delay} 秒 · 节流窗口 ${cfg.web_crawler_autothrottle_window} · 上限 ${cfg.web_crawler_autothrottle_max_delay}s`}
        />
        <ArrowDown />
        {target > 0 ? (
          <>
            <Decision text={`本批入库 ≥ ${target}？`} />
            <ArrowDown />
            <Junction pair>
              <Branch label="已达上限">
                <Terminal text="本批收工" sub="可人工提高上限后继续" kind="muted" />
              </Branch>
              <Branch label="未达" main>
                {failGate}
              </Branch>
            </Junction>
          </>
        ) : (
          failGate
        )}
      </ChartShell>
    )
  }

  if (step === 'board_select') {
    return (
      <ChartShell hint="本站一次只跑一个工作板（板块列表单选）；策略来自白名单板块策略">
        <Process text="读取工作板块" sub={board ? `${board.name} · 版块号 ${board.fid}` : '未选择'} />
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
    return (
      <ChartShell hint={`扫列表：统一 orderby=dateline（发帖时间）；浏览器读 HTML；最多深扫 ${pages} 页`}>
        <Process
          text="拼列表地址"
          sub={
            board?.fid === '95'
              ? '分类 716 · 按发帖时间排序'
              : '按发帖时间排序 · 第 n 页'
          }
        />
        <ArrowDown />
        <Process text="浏览器打开列表" sub="复用进站会话" />
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
                text="解析帖链"
                sub={
                  board?.fid === '141'
                    ? '跳过置顶 · 满 3 天龄期过滤'
                    : '跳过置顶 · 按发帖时间序'
                }
              />
              <ArrowDown />
              <Decision text="有新帖号？" />
              <ArrowDown />
              <Junction pair>
                <Branch label="无">
                  <Terminal text="翻下一页" sub={`最多 ${pages} 页`} kind="muted" />
                </Branch>
                <Branch label="有" main>
                  <Terminal text="写入待抓队列" sub="持久队列 · 进入抓帖" kind="ok" />
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
    const attachHint =
      board?.primary_link === 'ed2k'
        ? '正文无电驴 → 下尾部 txt/压缩包（需回复贴则不下）'
        : '正文无磁力 → 下 .torrent 转磁力'
    return (
      <ChartShell hint="抓帖：HTTP 取页 → 软文/壳则浏览器整页重读 → 再判定（跳过 / 失败 / 正常 / 占位 / 下附件 / 重试）">
        <Process text="HTTP 读取帖页" sub="会话内请求 · 附带进站 Cookie" />
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
                  <Terminal text="保留重试" sub="软文队列 · 下轮再抓" kind="warn" />
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
                          <Process text="抽正文 + 双链解析" sub={`目标主链：${prefer}`} />
                          <ArrowDown />
                          <Decision text="正文已有目标链接？" />
                          <ArrowDown />
                          <Junction pair>
                            <Branch label="有" main>
                              <Terminal text="进入入库" sub="正常候选" kind="ok" />
                            </Branch>
                            <Branch label="无">
                              <Spine>
                                <Process text="附件策略" sub={attachHint} />
                                <ArrowDown />
                                <Decision text="附件结果？" />
                                <ArrowDown />
                                <Junction cols={3}>
                                  <Branch label="解析出链接">
                                    <Terminal text="进入入库" sub="正文+附件合并" kind="ok" />
                                  </Branch>
                                  <Branch label="无权限">
                                    <Terminal text="占位入库" sub="无权限下载附件" kind="warn" />
                                  </Branch>
                                  <Branch label="失败/未出链" main>
                                    <Terminal text="保留重试" sub="附件失败或标题暗示有资源" kind="warn" />
                                  </Branch>
                                </Junction>
                                <ArrowDown />
                                <Decision text="仍无目标链时？" />
                                <ArrowDown />
                                <Junction cols={3}>
                                  <Branch label="需回复/购买">
                                    <Terminal text="占位入库" sub="需回复贴 / 需购买贴" kind="warn" />
                                  </Branch>
                                  <Branch label="网盘分享/非资源">
                                    <Terminal text="跳过" sub="非目标板资源 · 不再爬" kind="muted" />
                                  </Branch>
                                  <Branch label="其它" main>
                                    <Terminal
                                      text="保留重试"
                                      sub={
                                        board?.fid === '95'
                                          ? '无链 / 非情色分享待复核（仅本板）'
                                          : '无链 / 标题暗示有资源'
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
      </ChartShell>
    )
  }

  // import
  return (
    <ChartShell hint="入库出口：正常写主资源；占位写无链占位地址；失败不写；跳过/重试不入库">
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
            <Terminal text="不写资源表" sub="跳过·结束 · 失败·记错 · 重试·仍挂起" kind="muted" />
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
  const board = boards.find((b) => b.fid === activeBoardFid)
  const pages = cfg.web_crawler_list_pages_per_board || 15
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
        : '已关闭',
      status: enabled ? 'active' : 'idle',
    },
    {
      id: 'board_select',
      label: '选板',
      detail: board ? `${board.name}（仅此板）` : '未选择',
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
      detail: `发帖时间序 · 最多 ${pages} 页`,
      status: 'idle',
    },
    {
      id: 'thread_crawl',
      label: '抓帖',
      detail: 'HTTP · 软文浏览器重读 · 判定',
      status: 'idle',
    },
    {
      id: 'import',
      label: '入库',
      detail: '正常·占位·或跳过不写',
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
}

export function ForumTopology({ forum, activeForumId, boards, activeBoardFid }: Props) {
  const [params, setParams] = useSearchParams()
  const step = parseStep(params.get('step'))
  const cfg = forum.crawler_config
  const enabled = !!cfg.web_crawler_enabled && activeForumId === forum.id
  const isActiveForum = activeForumId === forum.id
  const board = boards.find((b) => b.fid === activeBoardFid)
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
            本站管线 · 仅 1 工作板 · 发帖时间序列表 · 帖子 HTTP
          </span>
          {board ? <span className="crawl-topo-current">当前 · {board.name}</span> : null}
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
