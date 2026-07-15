import { Fragment, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import {
  setActiveBoard,
  type ForumBoard,
  type ForumCrawlerConfig,
  type ForumFormatGuide,
  type ForumItem,
} from '../api/forums'
import { toast } from '../ui/toast'
import { ForumTopology } from './ForumTopology'

export type ForumTab = 'overview' | 'boards' | 'structure' | 'topology' | 'config'

type Props = {
  forum: ForumItem & { crawler_config: ForumCrawlerConfig }
  activeForumId: string
  tab: ForumTab
  onTabChange: (tab: ForumTab) => void
  onClose: () => void
  onSaveConfig: (config: ForumCrawlerConfig) => Promise<void>
  onActiveBoardChange: (config: ForumCrawlerConfig) => void
}

const TABS: { id: ForumTab; label: string }[] = [
  { id: 'overview', label: '概览' },
  { id: 'boards', label: '板块列表' },
  { id: 'structure', label: '结构化标签' },
  { id: 'topology', label: '执行拓扑' },
  { id: 'config', label: '爬虫配置' },
]

const FALLBACK_STRUCTURE_LABELS = [
  '影片名称',
  '资源名称',
  '影片容量',
  '资源大小',
  '是否有码',
  '有无水印',
  '出演女优',
  '解压密码',
]

function boardLinkLabel(kind: string) {
  if (kind === 'magnet') return '磁力'
  if (kind === 'ed2k') return 'ED2K'
  if (kind === 'both' || kind === 'mixed') return '双链'
  return kind
}

function groupBoards(boards: ForumBoard[]) {
  const order = ['综合讨论区', '原创BT电影']
  const groups = new Map<string, ForumBoard[]>()
  for (const board of boards) {
    const key = board.category || '其他'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(board)
  }
  const result: [string, ForumBoard[]][] = []
  for (const key of order) {
    if (groups.has(key)) {
      result.push([key, groups.get(key)!])
      groups.delete(key)
    }
  }
  for (const entry of groups.entries()) result.push(entry)
  return result
}

function Field({
  label,
  hint,
  full,
  children,
}: {
  label: string
  hint?: string
  full?: boolean
  children: ReactNode
}) {
  return (
    <label className={full ? 'forum-field-block forum-field-block--full' : 'forum-field-block'}>
      <span className="forum-field-label">{label}</span>
      {children}
      <small className="field-hint">{hint || '\u00a0'}</small>
    </label>
  )
}

function OverviewTab({
  forum,
  onGoto,
}: {
  forum: ForumItem & { crawler_config: ForumCrawlerConfig }
  onGoto: (tab: ForumTab) => void
}) {
  const boards = forum.boards || []
  const magnetCount = boards.filter((b) => b.primary_link === 'magnet').length
  const ed2kCount = boards.filter((b) => b.primary_link === 'ed2k').length
  const cfg = forum.crawler_config

  return (
    <div className="forum-overview">
      <div className="forum-modal-stats">
        <div className="forum-stat-pill forum-stat-pill--boards">
          <span className="forum-stat-val">{boards.length}</span>
          <span className="forum-stat-lbl">白名单板块</span>
        </div>
        <div className="forum-stat-pill forum-stat-pill--magnet">
          <span className="forum-stat-val">{magnetCount}</span>
          <span className="forum-stat-lbl">磁力板块</span>
        </div>
        <div className="forum-stat-pill forum-stat-pill--ed2k">
          <span className="forum-stat-val">{ed2kCount}</span>
          <span className="forum-stat-lbl">ED2K 板块</span>
        </div>
        <div className="forum-stat-pill forum-stat-pill--skip">
          <span className="forum-stat-val">4</span>
          <span className="forum-stat-lbl">跳过分区</span>
        </div>
      </div>

      <div className="forum-tab-content forum-overview-body">
        <section className="forum-modal-block">
          <div className="forum-block-head-inline">
            <h4>当前配置</h4>
            <button type="button" className="btn ghost sm" onClick={() => onGoto('config')}>
              编辑
            </button>
          </div>
          <div className="forum-config-summary">
            <div className="forum-config-summary-item">
              <span className="lbl">爬虫开关</span>
              <span className={`val ${cfg.web_crawler_enabled ? 'val-on' : 'val-off'}`}>
                {cfg.web_crawler_enabled ? '开启' : '关闭'}
              </span>
            </div>
            <div className="forum-config-summary-item">
              <span className="lbl">调度节奏</span>
              <span className="val">连续无间隔 · 延迟 {cfg.web_crawler_request_delay}s</span>
            </div>
            <div className="forum-config-summary-item">
              <span className="lbl">工作板块</span>
              <span className="val">
                {boards.find((b) => b.fid === cfg.active_board_fid)?.name || cfg.active_board_fid || '—'}
              </span>
            </div>
            <div className="forum-config-summary-item">
              <span className="lbl">扫列表</span>
              <span className="val">发帖时间序 · 每批 {cfg.web_crawler_list_pages_per_board || 15} 页</span>
            </div>
            <div className="forum-config-summary-item">
              <span className="lbl">抓帖</span>
              <span className="val">HTTP · 软文浏览器重读</span>
            </div>
            <div className="forum-config-summary-item">
              <span className="lbl">入库</span>
              <span className="val">每帖 1 主资源</span>
            </div>
            <div className="forum-config-summary-item full">
              <span className="lbl">入口 URL（含备用）</span>
              <span className="val mono forum-entry-urls">
                {(cfg.web_crawl_urls || '')
                  .split(',')
                  .map((u) => u.trim())
                  .filter(Boolean)
                  .map((u) => (
                    <span key={u}>{u}</span>
                  ))}
                {!cfg.web_crawl_urls?.trim() ? '—' : null}
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function StructureTab({
  guides,
  labels,
  boards,
}: {
  guides: ForumFormatGuide[]
  labels: string[]
  boards: ForumBoard[]
}) {
  const nameByFid = useMemo(() => {
    const map = new Map<string, string>()
    for (const b of boards) map.set(b.fid, b.name)
    return map
  }, [boards])

  return (
    <div className="forum-tab-content forum-tab-content-compact forum-tab-content--structure">
      <section className="forum-format-block">
        <div className="forum-block-head-inline">
          <h4>常用【标签】</h4>
        </div>
        <p className="hint forum-format-lead">按行识别「【标签】值」，不要求齐全；命中则规范化入库。</p>
        <div className="structure-label-chips" aria-label="常用结构化标签">
          {labels.map((label) => (
            <code key={label} className="structure-label-chip">
              【{label}】
            </code>
          ))}
        </div>
      </section>

      <section className="forum-format-block">
        <div className="forum-block-head-inline">
          <h4>板块解析差异</h4>
          <span className="forum-format-count">{guides.length} 类</span>
        </div>
        {guides.length === 0 ? (
          <p className="hint warn">暂无解析说明</p>
        ) : (
          <div className="format-guide-grid format-guide-grid-compact">
            {guides.map((guide) => {
              const fids = guide.fids || []
              const linkKind =
                guide.primary_link === 'ed2k' ? 'ed2k' : guide.primary_link === 'magnet' ? 'magnet' : 'stub'
              return (
                <article
                  key={guide.id}
                  className={`format-guide-card ${
                    guide.primary_link === 'ed2k' ? 'format-ed2k' : 'format-magnet'
                  }`}
                >
                  <div className="format-guide-head">
                    <h4>{guide.title}</h4>
                    <span className={`tag tag-${linkKind}`}>{boardLinkLabel(guide.primary_link)}</span>
                  </div>
                  {fids.length > 0 ? (
                    <div className="format-guide-fid-chips" aria-label="适用板块">
                      {fids.map((fid) => (
                        <span key={fid} className="format-guide-fid-chip">
                          {nameByFid.get(fid) || `fid ${fid}`}
                          <code>{fid}</code>
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <p className="format-guide-summary">{guide.summary}</p>
                  {(guide.fields || []).length > 0 ? (
                    <div className="format-guide-block">
                      <span className="format-guide-label">字段</span>
                      <ul className="format-guide-list">
                        {(guide.fields || []).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {(guide.notes || []).length > 0 ? (
                    <div className="format-guide-block">
                      <span className="format-guide-label">规则</span>
                      <ul className="format-guide-list muted">
                        {(guide.notes || []).map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </article>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}

function BoardsTab({
  forumId,
  boards,
  activeBoardFid,
  onSelect,
}: {
  forumId: string
  boards: ForumBoard[]
  activeBoardFid: string
  onSelect: (fid: string) => void
}) {
  const magnetCount = boards.filter((b) => b.primary_link === 'magnet').length
  const ed2kCount = boards.filter((b) => b.primary_link === 'ed2k').length
  const active = boards.find((b) => b.fid === activeBoardFid)
  const groups = groupBoards(boards)

  return (
    <div className="forum-tab-content forum-tab-content--boards">
      <section className="forum-modal-block forum-boards-block">
        <div className="forum-boards-toolbar">
          <div className="forum-boards-toolbar-main">
            <p className="hint">
              共 {boards.length} 个白名单板块 · 磁力 {magnetCount} · ED2K {ed2kCount} · 点选即可切换工作板块
            </p>
            <div className="forum-boards-active-card">
              <span className="forum-boards-active-lbl">当前工作板块</span>
              {active ? (
                <div className="forum-boards-active-val">
                  <strong>{active.name}</strong>
                  <code>fid={active.fid}</code>
                  {active.category ? <span className="tag">{active.category}</span> : null}
                  <span
                    className={`tag tag-${active.primary_link === 'ed2k' ? 'ed2k' : active.primary_link === 'magnet' ? 'magnet' : 'stub'}`}
                  >
                    {boardLinkLabel(active.primary_link)}
                  </span>
                </div>
              ) : (
                <span className="hint warn">未选择</span>
              )}
            </div>
          </div>
        </div>

        <div className="table-wrap forum-boards-table-wrap">
          <table className="data-table forum-boards-table">
            <colgroup>
              <col className="col-select" />
              <col className="col-fid" />
              <col className="col-name" />
              <col className="col-link" />
              <col className="col-count" />
              <col className="col-time" />
            </colgroup>
            <thead>
              <tr>
                <th className="board-select-cell">选择</th>
                <th className="board-col-fid">fid</th>
                <th className="board-col-name">名称</th>
                <th className="board-col-link">主链接</th>
                <th className="board-col-count" title="已爬取帖子数">
                  已爬取
                </th>
                <th className="board-col-time">上次爬取</th>
              </tr>
            </thead>
            <tbody data-forum-boards={forumId}>
              {groups.map(([category, items]) => (
                <Fragment key={category}>
                  <tr className="forum-board-category-row">
                    <td colSpan={6}>
                      <span className="forum-board-category-label">{category}</span>
                      <span className="forum-board-category-count">{items.length} 板</span>
                    </td>
                  </tr>
                  {items.map((b) => {
                    const selected = b.fid === activeBoardFid
                    return (
                      <tr
                        key={b.fid}
                        className={`forum-board-row${selected ? ' is-active-board' : ''}`}
                        data-board-fid={b.fid}
                        onClick={() => {
                          if (!selected) onSelect(b.fid)
                        }}
                      >
                        <td className="board-select-cell">
                          <label className="board-select-radio" title="设为当前工作板块">
                            <input
                              type="radio"
                              name={`active_board_${forumId}`}
                              value={b.fid}
                              checked={selected}
                              onChange={() => onSelect(b.fid)}
                              onClick={(e) => e.stopPropagation()}
                            />
                            <span className="board-select-dot" aria-hidden />
                          </label>
                        </td>
                        <td className="board-col-fid">
                          <code>{b.fid}</code>
                        </td>
                        <td className="board-col-name">
                          <span className="board-name-text">{b.name}</span>
                          {b.hot ? <span className="tag tag-pending">热门</span> : null}
                          {selected ? <span className="tag tag-active">工作中</span> : null}
                        </td>
                        <td className="board-col-link">
                          <span
                            className={`tag tag-${b.primary_link === 'ed2k' ? 'ed2k' : b.primary_link === 'magnet' ? 'magnet' : 'stub'}`}
                          >
                            {boardLinkLabel(b.primary_link)}
                          </span>
                        </td>
                        <td className="board-col-count">—</td>
                        <td className="board-col-time">—</td>
                      </tr>
                    )
                  })}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

function ConfigTab({
  draft,
  setDraft,
  saving,
  onSubmit,
}: {
  draft: ForumCrawlerConfig
  setDraft: (next: ForumCrawlerConfig) => void
  saving: boolean
  onSubmit: (e: FormEvent) => void
}) {
  const setNum = (key: keyof ForumCrawlerConfig, value: string) => {
    const n = Number(value)
    setDraft({ ...draft, [key]: Number.isFinite(n) ? n : draft[key] })
  }

  return (
    <div className="forum-tab-content">
      <form className="forum-config-form" onSubmit={onSubmit}>
        <p className="hint" style={{ marginBottom: 12 }}>
          参数分组与「执行拓扑」一致：开关 → 调度 → 进站 → 扫列表 → 抓帖 → 入库。工作板请在「板块列表」单选。
        </p>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">①</span>
            <div>
              <h4>开关</h4>
              <p className="field-hint">总开关关闭则整条链路不调度（与活动页开关同源）。</p>
            </div>
          </div>
          <div className="forum-config-grid forum-config-grid--single">
            <label className="forum-field-block forum-field-block--switch">
              <span className="forum-field-label">论坛爬虫开关</span>
              <div className="forum-field-control">
                <input
                  type="checkbox"
                  checked={!!draft.web_crawler_enabled}
                  onChange={(e) => setDraft({ ...draft, web_crawler_enabled: e.target.checked })}
                />
              </div>
              <small className="field-hint">{draft.web_crawler_enabled ? '开启 · 可进入调度' : '关闭 · 不调度'}</small>
            </label>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">②</span>
            <div>
              <h4>调度</h4>
              <p className="field-hint">连续执行、无轮间间隔；仅请求延迟 / 自动节流 / 失败冷却限速。</p>
            </div>
          </div>
          <div className="settings-grid-3 forum-config-grid">
            <Field label="轮间间隔" hint="本站固定 0（连续爬取）">
              <input type="number" min={0} max={0} value={0} readOnly disabled />
            </Field>
            <Field label="请求延迟（秒）" hint="帖间基准延迟，默认 2s">
              <input type="number" min={0.5} max={60} step={0.5} value={draft.web_crawler_request_delay} onChange={(e) => setNum('web_crawler_request_delay', e.target.value)} />
            </Field>
            <Field label="目标入库数" hint="0 = 不限，达上限停止本批">
              <input type="number" min={0} max={10000} value={draft.web_crawler_target_imports} onChange={(e) => setNum('web_crawler_target_imports', e.target.value)} />
            </Field>
            <Field label="连续失败阈值" hint="连续抓取失败达此次数后进入冷却">
              <input type="number" min={2} max={20} value={draft.web_crawler_fetch_failure_threshold} onChange={(e) => setNum('web_crawler_fetch_failure_threshold', e.target.value)} />
            </Field>
            <Field label="失败冷却（秒）" hint="触发冷却后暂停时长">
              <input type="number" min={15} max={600} value={draft.web_crawler_fetch_cooldown_seconds} onChange={(e) => setNum('web_crawler_fetch_cooldown_seconds', e.target.value)} />
            </Field>
            <Field label="每轮最大冷却" hint="冷却满次数仍失败则本轮熔断">
              <input type="number" min={1} max={10} value={draft.web_crawler_fetch_max_cooldowns} onChange={(e) => setNum('web_crawler_fetch_max_cooldowns', e.target.value)} />
            </Field>
            <Field label="自动节流上限（秒）" hint="失败率升高时动态延迟上限">
              <input type="number" min={5} max={300} value={draft.web_crawler_autothrottle_max_delay} onChange={(e) => setNum('web_crawler_autothrottle_max_delay', e.target.value)} />
            </Field>
            <Field label="自动节流采样窗口" hint="统计近 N 次请求成功率">
              <input type="number" min={5} max={100} value={draft.web_crawler_autothrottle_window} onChange={(e) => setNum('web_crawler_autothrottle_window', e.target.value)} />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">③</span>
            <div>
              <h4>进站</h4>
              <p className="field-hint">入口 URL / Cookie / UA；HTTP 代理在「系统设置 → 通用配置」。</p>
            </div>
          </div>
          <div className="settings-grid-2 forum-config-grid">
            <Field label="入口 URL" hint="逗号分隔；主站失效时按序尝试备用域名" full>
              <textarea
                rows={3}
                className="forum-entry-urls-field"
                spellCheck={false}
                value={draft.web_crawl_urls}
                placeholder="https://www.sehuatang.net/forum.php, https://www.sehuatang.org/forum.php, …"
                onChange={(e) => setDraft({ ...draft, web_crawl_urls: e.target.value })}
              />
            </Field>
            <Field label="请求超时（秒）" hint="单次浏览器/HTTP 请求上限">
              <input type="number" min={5} max={300} value={draft.web_crawler_timeout} onChange={(e) => setNum('web_crawler_timeout', e.target.value)} />
            </Field>
            <Field label="取页重试次数" hint="HTTP/浏览器单次请求失败重试">
              <input type="number" min={1} max={10} value={draft.web_crawler_fetch_retries} onChange={(e) => setNum('web_crawler_fetch_retries', e.target.value)} />
            </Field>
            <Field label="User-Agent" full>
              <input type="text" value={draft.web_crawler_ua} onChange={(e) => setDraft({ ...draft, web_crawler_ua: e.target.value })} />
            </Field>
            <Field label="论坛 Cookie" hint="登录后复制；列表需登录时必须填写" full>
              <textarea
                rows={4}
                className="forum-cookie-field"
                spellCheck={false}
                placeholder="safe=1; bbs_sid=...; 粘贴浏览器完整 Cookie"
                value={draft.web_crawler_cookie}
                onChange={(e) => setDraft({ ...draft, web_crawler_cookie: e.target.value })}
              />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">④</span>
            <div>
              <h4>扫列表</h4>
              <p className="field-hint">
                每日一次从首页捕新（扫到整页已入库即停）；当天后续循环只深扫。深扫结束页重叠 1 页。
              </p>
            </div>
          </div>
          <div className="settings-grid-2 forum-config-grid">
            <Field label="列表页数 / 批" hint="深扫每批向前页数，默认 15">
              <input type="number" min={1} max={100} value={draft.web_crawler_list_pages_per_board} onChange={(e) => setNum('web_crawler_list_pages_per_board', e.target.value)} />
            </Field>
            <Field label="首页捕新安全上限" hint="每日首页最多翻 N 页；通常扫到全已知即停，默认 50">
              <input
                type="number"
                min={1}
                max={100}
                value={draft.web_crawler_list_head_pages ?? 50}
                onChange={(e) => setNum('web_crawler_list_head_pages', e.target.value)}
              />
            </Field>
            <Field label="深扫早停页数" hint="连续 N 页全已知则提前结束本轮深扫，默认 2">
              <input
                type="number"
                min={1}
                max={10}
                value={draft.web_crawler_list_known_stop_pages ?? 2}
                onChange={(e) => setNum('web_crawler_list_known_stop_pages', e.target.value)}
              />
            </Field>
            <Field label="全局列表页上限" hint="0 = 安全上限 300 页/板">
              <input type="number" min={0} max={300} value={draft.web_crawler_max_list_pages} onChange={(e) => setNum('web_crawler_max_list_pages', e.target.value)} />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">⑤</span>
            <div>
              <h4>抓帖</h4>
              <p className="field-hint">HTTP 读帖；遇软文/安全壳自动浏览器整页重读后再判定。</p>
            </div>
          </div>
          <div className="settings-grid-2 forum-config-grid">
            <Field label="单帖超时（秒）" hint="0 = 不限；默认 120">
              <input type="number" min={0} max={900} value={draft.web_crawler_thread_timeout} onChange={(e) => setNum('web_crawler_thread_timeout', e.target.value)} />
            </Field>
            <Field label="取页策略" hint="与拓扑定稿一致，不可改">
              <input type="text" value="列表浏览器 · 帖子 HTTP · 软文浏览器重读" readOnly disabled />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">⑥</span>
            <div>
              <h4>入库</h4>
              <p className="field-hint">正常写主资源；占位写无链地址；跳过/重试/失败不写。</p>
            </div>
          </div>
          <div className="forum-config-grid forum-config-grid--single">
            <label className="forum-field-block forum-field-block--switch">
              <span className="forum-field-label">每帖只入一条主资源</span>
              <div className="forum-field-control">
                <input type="checkbox" checked disabled title="拓扑定稿，不可关闭" />
              </div>
              <small className="field-hint">同帖全部链接写入 links 字段</small>
            </label>
          </div>
        </section>

        <div className="forum-modal-foot">
          <button type="submit" className="btn primary forum-save-btn" disabled={saving}>
            {saving ? '保存中…' : '保存论坛配置'}
          </button>
        </div>
      </form>
    </div>
  )
}

export function ForumConfigModal({
  forum,
  activeForumId,
  tab,
  onTabChange,
  onClose,
  onSaveConfig,
  onActiveBoardChange,
}: Props) {
  const [draft, setDraft] = useState<ForumCrawlerConfig>(() => ({ ...forum.crawler_config }))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setDraft({ ...forum.crawler_config })
  }, [forum])

  const isEnabled = activeForumId === forum.id
  const boards = useMemo(() => {
    const list = [...(forum.boards || [])]
    const order = forum.crawler_config.board_order || []
    if (!order.length) return list
    const byFid = new Map(list.map((b) => [b.fid, b]))
    const sorted: ForumBoard[] = []
    for (const fid of order) {
      const board = byFid.get(String(fid))
      if (board) {
        sorted.push(board)
        byFid.delete(String(fid))
      }
    }
    for (const board of byFid.values()) sorted.push(board)
    return sorted
  }, [forum.boards, forum.crawler_config.board_order])

  const activeBoardFid = draft.active_board_fid || forum.crawler_config.active_board_fid || boards[0]?.fid || ''

  const handleSelectBoard = (fid: string) => {
    if (fid === activeBoardFid) return
    const next = {
      ...draft,
      active_board_fid: fid,
      web_crawler_max_boards_per_run: 1,
    }
    setDraft(next)
    onActiveBoardChange(next)
    // 后台静默写入，无需点保存
    void setActiveBoard(forum.id, fid).then(
      (res) => onActiveBoardChange({ ...next, ...res.config }),
      () => {
        /* 失败时保留本地选中，下次保存配置时一并写回 */
      },
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload: ForumCrawlerConfig = {
        ...draft,
        active_board_fid: draft.active_board_fid || activeBoardFid,
        web_crawler_interval_minutes: 0,
        web_crawler_max_boards_per_run: 1,
        web_crawler_one_link_per_thread: true,
        web_crawler_require_structured_desc: false,
        web_crawler_auto_discover: false,
        web_crawler_max_threads_per_run: 0,
      }
      await onSaveConfig(payload)
      toast.success('论坛配置已保存')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (forum.status !== 'active') {
    return (
      <div className="modal-backdrop forum-modal-backdrop" onClick={onClose}>
        <div className="modal-card forum-modal-panel" onClick={(e) => e.stopPropagation()}>
          <div className="modal-head">
            <h3>{forum.name}</h3>
            <button type="button" className="btn ghost" onClick={onClose}>
              关闭
            </button>
          </div>
          <div className="modal-body">
            <p className="hint">{(forum.policies || [])[0] || '该论坛尚未接入'}</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-backdrop forum-modal-backdrop" onClick={onClose}>
      <div className="modal-card forum-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="forum-modal-title">
            <span className="forum-card-icon" aria-hidden>
              {forum.id === 'sehuatang' ? (
                <img src="/sehuatang-forum-icon.png" alt="" className="forum-card-icon-img" />
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M2 12h20M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
                </svg>
              )}
            </span>
            <div>
              <h3>{forum.name}</h3>
              <p className="forum-card-url">{forum.base_url}</p>
            </div>
            {isEnabled ? (
              <span className="tag tag-active">本站专用 · 当前启用</span>
            ) : (
              <span className="tag tag-done">本站专用爬虫</span>
            )}
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="forum-modal-body">
          <nav className="forum-tab-nav" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                className={tab === t.id ? 'forum-tab active' : 'forum-tab'}
                aria-selected={tab === t.id}
                onClick={() => onTabChange(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="forum-tab-panels">
            <div className={tab === 'overview' ? 'forum-tab-panel active' : 'forum-tab-panel'} role="tabpanel">
              {tab === 'overview' ? <OverviewTab forum={forum} onGoto={onTabChange} /> : null}
            </div>
            <div className={tab === 'boards' ? 'forum-tab-panel active' : 'forum-tab-panel'} role="tabpanel">
              {tab === 'boards' ? (
                <BoardsTab
                  forumId={forum.id}
                  boards={boards}
                  activeBoardFid={activeBoardFid}
                  onSelect={handleSelectBoard}
                />
              ) : null}
            </div>
            <div className={tab === 'structure' ? 'forum-tab-panel active' : 'forum-tab-panel'} role="tabpanel">
              {tab === 'structure' ? (
                <StructureTab
                  guides={forum.format_guides || []}
                  labels={forum.structure_labels?.length ? forum.structure_labels : FALLBACK_STRUCTURE_LABELS}
                  boards={boards}
                />
              ) : null}
            </div>
            <div className={tab === 'topology' ? 'forum-tab-panel active' : 'forum-tab-panel'} role="tabpanel">
              {tab === 'topology' ? (
                <ForumTopology
                  forum={forum}
                  activeForumId={activeForumId}
                  boards={boards}
                  activeBoardFid={activeBoardFid}
                />
              ) : null}
            </div>
            <div className={tab === 'config' ? 'forum-tab-panel active' : 'forum-tab-panel'} role="tabpanel">
              {tab === 'config' ? (
                <ConfigTab draft={draft} setDraft={setDraft} saving={saving} onSubmit={handleSubmit} />
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
