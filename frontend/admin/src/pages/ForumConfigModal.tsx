import { Fragment, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { fetchCrawlerStatus } from '../api/crawler'
import {
  clearBoardCursor,
  saveForumConfig,
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

/** 爬取单位 key：优先 API 的 key，否则 fid:typeid */
function boardUnitKey(b: ForumBoard): string {
  if (b.key) return b.key
  if (b.typeid) return `${b.fid}:${b.typeid}`
  return String(b.fid)
}

function boardUnitCode(b: ForumBoard): string {
  if (b.typeid) return `${b.fid}/${b.typeid}`
  return String(b.fid)
}

function boardParentName(b: ForumBoard): string {
  return (b.board_name || b.name.split('-')[0] || b.name).trim()
}

type ParentBoardGroup = {
  fid: string
  name: string
  category: string
  primary_link: string
  children: ForumBoard[]
}

function groupParentBoards(boards: ForumBoard[]): [string, ParentBoardGroup[]][] {
  const categoryOrder = ['综合讨论区', '原创BT电影']
  const parents = new Map<string, ParentBoardGroup>()
  for (const board of boards) {
    const fid = String(board.fid)
    let parent = parents.get(fid)
    if (!parent) {
      parent = {
        fid,
        name: boardParentName(board),
        category: board.category || '其他',
        primary_link: board.primary_link,
        children: [],
      }
      parents.set(fid, parent)
    }
    parent.children.push(board)
  }
  for (const p of parents.values()) {
    p.children.sort((a, b) => (a.priority ?? 50) - (b.priority ?? 50) || a.name.localeCompare(b.name, 'zh-CN'))
  }
  const byCat = new Map<string, ParentBoardGroup[]>()
  for (const p of parents.values()) {
    if (!byCat.has(p.category)) byCat.set(p.category, [])
    byCat.get(p.category)!.push(p)
  }
  for (const list of byCat.values()) {
    list.sort((a, b) => Number(a.fid) - Number(b.fid) || a.name.localeCompare(b.name, 'zh-CN'))
  }
  const result: [string, ParentBoardGroup[]][] = []
  for (const key of categoryOrder) {
    if (byCat.has(key)) {
      result.push([key, byCat.get(key)!])
      byCat.delete(key)
    }
  }
  for (const entry of byCat.entries()) result.push(entry)
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
          <span className="forum-stat-lbl">白名单子版</span>
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
              <span className="lbl">工作子版</span>
              <span className="val">
                {(() => {
                  const enabled = cfg.enabled_board_fids?.length
                    ? cfg.enabled_board_fids
                    : cfg.active_board_fid
                      ? [cfg.active_board_fid]
                      : []
                  if (!enabled.length) return '—'
                  const names = enabled.map(
                    (fid) => boards.find((b) => boardUnitKey(b) === fid)?.name || fid,
                  )
                  const current =
                    boards.find((b) => boardUnitKey(b) === cfg.active_board_fid)?.name ||
                    cfg.active_board_fid
                  const shown = names.slice(0, 6).join(' → ')
                  const more = names.length > 6 ? ` …(+${names.length - 6})` : ''
                  return `${enabled.length} 子版启用 · 深扫当前 ${current || '—'} · ${shown}${more}`
                })()}
              </span>
            </div>
            <div className="forum-config-summary-item">
              <span className="lbl">扫列表</span>
              <span className="val">发帖时间序 · 深扫每轮 {cfg.web_crawler_list_pages_per_board || 15} 页至板底</span>
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
  enabledFids,
  activeBoardFid,
  cursors,
  onToggle,
  onToggleMany,
  onSetCurrent,
  onClearCursor,
}: {
  forumId: string
  boards: ForumBoard[]
  enabledFids: string[]
  activeBoardFid: string
  cursors: Record<string, number>
  onToggle: (fid: string, enabled: boolean) => void
  onToggleMany?: (fids: string[], enabled: boolean) => void
  onSetCurrent: (fid: string) => void
  onClearCursor: (fid: string) => void
}) {
  const magnetCount = boards.filter((b) => b.primary_link === 'magnet').length
  const ed2kCount = boards.filter((b) => b.primary_link === 'ed2k').length
  const enabledSet = useMemo(() => new Set(enabledFids.map(String)), [enabledFids])
  const queueIndex = useMemo(() => {
    const map = new Map<string, number>()
    enabledFids.forEach((fid, i) => map.set(String(fid), i + 1))
    return map
  }, [enabledFids])
  const active = boards.find((b) => boardUnitKey(b) === activeBoardFid)
  const tree = useMemo(() => groupParentBoards(boards), [boards])
  const parentCount = useMemo(() => tree.reduce((n, [, list]) => n + list.length, 0), [tree])

  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const [clearing, setClearing] = useState<string | null>(null)

  function cursorPage(key: string): number {
    try {
      return Math.max(0, Number(cursors[key] || 0))
    } catch {
      return 0
    }
  }

  function toggleExpand(fid: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(fid)) next.delete(fid)
      else next.add(fid)
      return next
    })
  }

  function toggleParentAll(parent: ParentBoardGroup, enable: boolean) {
    const keys = parent.children.map(boardUnitKey)
    if (onToggleMany) {
      onToggleMany(keys, enable)
      return
    }
    for (const key of keys) {
      if (enable !== enabledSet.has(key)) onToggle(key, enable)
    }
  }

  function handleClear(key: string) {
    if (!key || clearing) return
    setClearing(key)
    void Promise.resolve(onClearCursor(key)).finally(() => setClearing(null))
  }

  function CursorCell({ unitKey }: { unitKey: string }) {
    const page = cursorPage(unitKey)
    return (
      <div className="board-cursor-cell" onClick={(e) => e.stopPropagation()}>
        <span className="board-cursor-page" title={page > 0 ? `深扫游标第 ${page} 页（到底后仍保留，仅手动清除）` : '尚未深扫 / 已清游标'}>
          {page > 0 ? `P${page}` : '—'}
        </span>
        <button
          type="button"
          className="btn sm secondary"
          disabled={page <= 0 || clearing === unitKey}
          title="清除游标后，下次深扫从第 1 页起；已有资源只改板块名，缺失才抓帖"
          onClick={(e) => {
            e.stopPropagation()
            handleClear(unitKey)
          }}
        >
          {clearing === unitKey ? '…' : '清除'}
        </button>
      </div>
    )
  }

  return (
    <div className="forum-tab-content forum-tab-content--boards">
      <section className="forum-modal-block forum-boards-block">
        <div className="forum-boards-toolbar">
          <div className="forum-boards-toolbar-main">
            <p className="hint">
              {parentCount} 个主板块 · {boards.length} 个分类子版 · 磁力 {magnetCount} · ED2K {ed2kCount}
              · 点击主板块展开子版
            </p>
            <div className="forum-boards-active-card">
              <span className="forum-boards-active-lbl">启用队列 · {enabledFids.length} 子版</span>
              {enabledFids.length ? (
                <div className="forum-boards-active-val">
                  <strong className="forum-boards-queue-path" title={enabledFids.join(' → ')}>
                    {enabledFids
                      .map((fid) => boards.find((b) => boardUnitKey(b) === fid)?.name || fid)
                      .join(' → ')}
                  </strong>
                  {active ? (
                    <span className="tag tag-active" title="深扫当前子版">
                      深扫当前 · {active.name}
                    </span>
                  ) : null}
                </div>
              ) : (
                <span className="hint warn">请至少勾选一个工作子版</span>
              )}
            </div>
          </div>
        </div>

        <div className="table-wrap forum-boards-table-wrap">
          <table className="data-table forum-boards-table forum-boards-table--tree">
            <colgroup>
              <col className="col-select" />
              <col className="col-fid" />
              <col className="col-name" />
              <col className="col-link" />
              <col className="col-count" />
              <col className="col-cursor" />
              <col className="col-time" />
            </colgroup>
            <thead>
              <tr>
                <th className="board-select-cell">启用</th>
                <th className="board-col-fid">分类</th>
                <th className="board-col-name">板块</th>
                <th className="board-col-link">主链接</th>
                <th className="board-col-count" title="队列顺序">
                  顺序
                </th>
                <th className="board-col-cursor" title="深扫列表游标页；到底后仍保留，仅手动清除后从第 1 页重扫">
                  游标
                </th>
                <th className="board-col-time">深扫当前</th>
              </tr>
            </thead>
            <tbody data-forum-boards={forumId}>
              {tree.map(([category, parents]) => (
                <Fragment key={category}>
                  <tr className="forum-board-category-row">
                    <td colSpan={7}>
                      <span className="forum-board-category-label">{category}</span>
                      <span className="forum-board-category-count">
                        {parents.length} 主板块 · {parents.reduce((n, p) => n + p.children.length, 0)}{' '}
                        子版
                      </span>
                    </td>
                  </tr>
                  {parents.map((parent) => {
                    const childKeys = parent.children.map(boardUnitKey)
                    const enabledKids = childKeys.filter((k) => enabledSet.has(k))
                    const allOn = enabledKids.length === childKeys.length && childKeys.length > 0
                    const someOn = enabledKids.length > 0 && !allOn
                    const isOpen = expanded.has(parent.fid)
                    const hasSubTypes = parent.children.some((c) => Boolean(c.typeid))
                    const sole = parent.children.length === 1 && !hasSubTypes ? parent.children[0] : null
                    const soleKey = sole ? boardUnitKey(sole) : ''
                    const soleSelected = sole ? enabledSet.has(soleKey) : false
                    const soleCurrent = sole ? soleKey === activeBoardFid : false
                    const parentHasActive = childKeys.includes(activeBoardFid)

                    return (
                      <Fragment key={parent.fid}>
                        <tr
                          className={`forum-board-row forum-board-parent-row${allOn || someOn ? ' is-active-board' : ''}${parentHasActive ? ' is-current-parent' : ''}${soleCurrent ? ' is-current-board' : ''}`}
                          data-board-fid={parent.fid}
                          onClick={() => {
                            if (sole) onToggle(soleKey, !soleSelected)
                            else toggleExpand(parent.fid)
                          }}
                          style={{ cursor: 'pointer' }}
                        >
                          <td className="board-select-cell">
                            <label
                              className="board-select-check"
                              title={sole ? '启用本板块' : allOn ? '取消全部子版' : '启用全部子版'}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                type="checkbox"
                                checked={sole ? soleSelected : allOn}
                                ref={(el) => {
                                  if (el && !sole) el.indeterminate = someOn
                                }}
                                onChange={(e) => {
                                  e.stopPropagation()
                                  if (sole) onToggle(soleKey, e.target.checked)
                                  else toggleParentAll(parent, e.target.checked)
                                }}
                                onClick={(e) => e.stopPropagation()}
                              />
                              <span className="board-select-box" aria-hidden />
                            </label>
                          </td>
                          <td className="board-col-fid">
                            <code>{parent.fid}</code>
                          </td>
                          <td className="board-col-name">
                            <div className="board-name-inner">
                              {!sole ? (
                                <button
                                  type="button"
                                  className={`forum-board-expand${isOpen ? ' is-open' : ''}`}
                                  aria-expanded={isOpen}
                                  title={isOpen ? '收起子版' : '展开子版'}
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    toggleExpand(parent.fid)
                                  }}
                                >
                                  <span className="forum-board-expand-icon" aria-hidden />
                                </button>
                              ) : (
                                <span className="forum-board-expand-spacer" aria-hidden />
                              )}
                              <span className="board-name-text">{parent.name}</span>
                              <span
                                className={`tag board-link-inline tag-${parent.primary_link === 'ed2k' ? 'ed2k' : parent.primary_link === 'magnet' ? 'magnet' : 'stub'}`}
                              >
                                {boardLinkLabel(parent.primary_link)}
                              </span>
                              <span className="board-name-meta">
                                {!sole ? (
                                  <span className="tag tag-muted">
                                    {enabledKids.length}/{parent.children.length} 子版
                                  </span>
                                ) : null}
                                {someOn ? <span className="tag tag-partial">部分</span> : null}
                                {parentHasActive ? <span className="tag tag-scan">深扫中</span> : null}
                              </span>
                            </div>
                          </td>
                          <td className="board-col-link">
                            <span
                              className={`tag tag-${parent.primary_link === 'ed2k' ? 'ed2k' : parent.primary_link === 'magnet' ? 'magnet' : 'stub'}`}
                            >
                              {boardLinkLabel(parent.primary_link)}
                            </span>
                          </td>
                          <td className="board-col-count">
                            {sole ? (queueIndex.get(soleKey) ?? '—') : null}
                          </td>
                          <td className="board-col-cursor">
                            {sole ? <CursorCell unitKey={soleKey} /> : null}
                          </td>
                          <td className="board-col-time">
                            {sole && soleSelected ? (
                              <button
                                type="button"
                                className={`btn sm ${soleCurrent ? 'primary' : 'secondary'}`}
                                disabled={soleCurrent}
                                title="设为深扫当前"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onSetCurrent(soleKey)
                                }}
                              >
                                {soleCurrent ? '当前' : '设为当前'}
                              </button>
                            ) : null}
                          </td>
                        </tr>
                        {isOpen && !sole
                          ? parent.children.map((b) => {
                              const unitKey = boardUnitKey(b)
                              const selected = enabledSet.has(unitKey)
                              const isCurrent = unitKey === activeBoardFid
                              const ord = queueIndex.get(unitKey)
                              const typeLabel = b.type_name || b.name
                              return (
                                <tr
                                  key={unitKey}
                                  className={`forum-board-row forum-board-child-row${selected ? ' is-active-board' : ''}${isCurrent ? ' is-current-board' : ''}`}
                                  data-board-fid={unitKey}
                                  onClick={() => onToggle(unitKey, !selected)}
                                  style={{ cursor: 'pointer' }}
                                >
                                  <td className="board-select-cell">
                                    <label
                                      className="board-select-check"
                                      title="勾选加入爬取队列"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <input
                                        type="checkbox"
                                        checked={selected}
                                        onChange={(e) => {
                                          e.stopPropagation()
                                          onToggle(unitKey, e.target.checked)
                                        }}
                                        onClick={(e) => e.stopPropagation()}
                                      />
                                      <span className="board-select-box" aria-hidden />
                                    </label>
                                  </td>
                                  <td className="board-col-fid">
                                    <code>{boardUnitCode(b)}</code>
                                  </td>
                                  <td className="board-col-name">
                                    <div className="board-name-inner board-name-inner--child">
                                      <span className="forum-board-child-indent" aria-hidden />
                                      <span className="board-name-text">{typeLabel}</span>
                                      <span
                                        className={`tag board-link-inline tag-${b.primary_link === 'ed2k' ? 'ed2k' : b.primary_link === 'magnet' ? 'magnet' : 'stub'}`}
                                      >
                                        {boardLinkLabel(b.primary_link)}
                                      </span>
                                      <span className="board-name-meta">
                                        {isCurrent ? <span className="tag tag-scan">深扫中</span> : null}
                                      </span>
                                    </div>
                                  </td>
                                  <td className="board-col-link">
                                    <span
                                      className={`tag tag-${b.primary_link === 'ed2k' ? 'ed2k' : b.primary_link === 'magnet' ? 'magnet' : 'stub'}`}
                                    >
                                      {boardLinkLabel(b.primary_link)}
                                    </span>
                                  </td>
                                  <td className="board-col-count">{ord ?? '—'}</td>
                                  <td className="board-col-cursor">
                                    <CursorCell unitKey={unitKey} />
                                  </td>
                                  <td className="board-col-time">
                                    {selected ? (
                                      <button
                                        type="button"
                                        className={`btn sm ${isCurrent ? 'primary' : 'secondary'}`}
                                        disabled={isCurrent}
                                        title="设为深扫当前子版"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          onSetCurrent(unitKey)
                                        }}
                                      >
                                        {isCurrent ? '当前' : '设为当前'}
                                      </button>
                                    ) : (
                                      '—'
                                    )}
                                  </td>
                                </tr>
                              )
                            })
                          : null}
                      </Fragment>
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
          从上到下：调速度 → 进论坛 → 扫列表找帖 → 抓帖内容 → 入库。开关在爬虫活动页；要爬哪些板，去「板块列表」勾选。
        </p>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">①</span>
            <div>
              <h4>调度</h4>
              <p className="field-hint">一直连着跑，中间不停歇。主要靠下面这些延迟、冷却来限速，避免封号。</p>
            </div>
          </div>
          <div className="settings-grid-3 forum-config-grid">
            <Field label="轮间间隔" hint="固定为 0，一轮完立刻下一轮">
              <input type="number" min={0} max={0} value={0} readOnly disabled />
            </Field>
            <Field label="请求延迟（秒）" hint="每抓一帖前后先等一会儿，默认 2 秒">
              <input type="number" min={0.5} max={60} step={0.5} value={draft.web_crawler_request_delay} onChange={(e) => setNum('web_crawler_request_delay', e.target.value)} />
            </Field>
            <Field label="目标入库数" hint="本轮最多入库几条；填 0 表示不限制">
              <input type="number" min={0} max={10000} value={draft.web_crawler_target_imports} onChange={(e) => setNum('web_crawler_target_imports', e.target.value)} />
            </Field>
            <Field label="连续失败阈值" hint="连续失败这么多次，就暂停一会儿">
              <input type="number" min={2} max={20} value={draft.web_crawler_fetch_failure_threshold} onChange={(e) => setNum('web_crawler_fetch_failure_threshold', e.target.value)} />
            </Field>
            <Field label="失败冷却（秒）" hint="暂停时一共歇多久">
              <input type="number" min={15} max={600} value={draft.web_crawler_fetch_cooldown_seconds} onChange={(e) => setNum('web_crawler_fetch_cooldown_seconds', e.target.value)} />
            </Field>
            <Field label="每轮最大冷却" hint="本轮暂停这么多次还不行，就停掉本轮">
              <input type="number" min={1} max={10} value={draft.web_crawler_fetch_max_cooldowns} onChange={(e) => setNum('web_crawler_fetch_max_cooldowns', e.target.value)} />
            </Field>
            <Field label="自动节流上限（秒）" hint="失败多了会自动多等一会儿，最多等到这个秒数">
              <input type="number" min={5} max={300} value={draft.web_crawler_autothrottle_max_delay} onChange={(e) => setNum('web_crawler_autothrottle_max_delay', e.target.value)} />
            </Field>
            <Field label="自动节流采样窗口" hint="用最近多少次请求来判断成功率">
              <input type="number" min={5} max={100} value={draft.web_crawler_autothrottle_window} onChange={(e) => setNum('web_crawler_autothrottle_window', e.target.value)} />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">②</span>
            <div>
              <h4>进站</h4>
              <p className="field-hint">怎么进论坛：地址、Cookie、浏览器标识。代理去「系统设置 → 通用配置」填。</p>
            </div>
          </div>
          <div className="settings-grid-2 forum-config-grid">
            <Field label="入口 URL" hint="多个地址用英文逗号隔开；前面的挂了会试后面的" full>
              <textarea
                rows={3}
                className="forum-entry-urls-field"
                spellCheck={false}
                value={draft.web_crawl_urls}
                placeholder="https://www.sehuatang.net/forum.php, https://www.sehuatang.org/forum.php, …"
                onChange={(e) => setDraft({ ...draft, web_crawl_urls: e.target.value })}
              />
            </Field>
            <Field label="请求超时（秒）" hint="单次打开网页最多等多久">
              <input type="number" min={5} max={300} value={draft.web_crawler_timeout} onChange={(e) => setNum('web_crawler_timeout', e.target.value)} />
            </Field>
            <Field label="取页重试次数" hint="打开失败时再试几次">
              <input type="number" min={1} max={10} value={draft.web_crawler_fetch_retries} onChange={(e) => setNum('web_crawler_fetch_retries', e.target.value)} />
            </Field>
            <Field label="浏览器标识（UA）" hint="伪装成普通浏览器访问" full>
              <input type="text" value={draft.web_crawler_ua} onChange={(e) => setDraft({ ...draft, web_crawler_ua: e.target.value })} />
            </Field>
            <Field label="论坛 Cookie" hint="普通爬虫用（匿名/过年龄门）；看列表要登录时可填" full>
              <textarea
                rows={4}
                className="forum-cookie-field"
                spellCheck={false}
                placeholder="safe=1; bbs_sid=...; 粘贴浏览器完整 Cookie"
                value={draft.web_crawler_cookie}
                onChange={(e) => setDraft({ ...draft, web_crawler_cookie: e.target.value })}
              />
            </Field>
            <Field
              label="账号 Cookie"
              hint="仅「账号爬占位」使用；浏览器登录论坛后复制完整 Cookie，与上方普通 Cookie 分开"
              full
            >
              <textarea
                rows={4}
                className="forum-cookie-field"
                spellCheck={false}
                placeholder="登录态 Cookie：bbs_sid=...; bbs_auth=...;"
                value={draft.web_crawler_account_cookie || ''}
                onChange={(e) => setDraft({ ...draft, web_crawler_account_cookie: e.target.value })}
              />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">③</span>
            <div>
              <h4>扫列表</h4>
              <p className="field-hint">从板块列表页找帖。「立即爬取」往深处翻；「扫新帖」从第 1 页抓新贴。</p>
            </div>
          </div>
          <div className="settings-grid-2 forum-config-grid">
            <Field label="每轮翻几页" hint="深扫一轮最多翻这么多页，下轮接着翻；默认 15">
              <input type="number" min={1} max={100} value={draft.web_crawler_list_pages_per_board} onChange={(e) => setNum('web_crawler_list_pages_per_board', e.target.value)} />
            </Field>
            <Field label="扫新帖页数（全局）" hint="点「扫新帖」时最多翻几页；默认 20">
              <input
                type="number"
                min={1}
                max={200}
                value={draft.web_crawler_manual_head_pages ?? 20}
                onChange={(e) => setNum('web_crawler_manual_head_pages', e.target.value)}
              />
            </Field>
            <Field
              label={`扫新帖页数（当前板 ${draft.active_board_fid || '—'}）`}
              hint="只改当前板；空白表示用上面的全局页数"
            >
              <input
                type="number"
                min={1}
                max={200}
                placeholder="用全局"
                value={
                  draft.active_board_fid && draft.board_manual_head_pages?.[String(draft.active_board_fid)] != null
                    ? draft.board_manual_head_pages[String(draft.active_board_fid)]
                    : ''
                }
                onChange={(e) => {
                  const fid = String(draft.active_board_fid || '').trim()
                  if (!fid) return
                  const map = { ...(draft.board_manual_head_pages || {}) }
                  const raw = e.target.value.trim()
                  if (!raw) {
                    delete map[fid]
                  } else {
                    const n = Number(raw)
                    if (Number.isFinite(n) && n >= 1) map[fid] = Math.floor(n)
                  }
                  setDraft({ ...draft, board_manual_head_pages: map })
                }}
              />
            </Field>
            <Field label="扫新帖早停页数" hint="连续这么多页看到的都是旧帖，就提前结束；默认 2">
              <input
                type="number"
                min={1}
                max={10}
                value={draft.web_crawler_list_known_stop_pages ?? 2}
                onChange={(e) => setNum('web_crawler_list_known_stop_pages', e.target.value)}
              />
            </Field>
            <Field label="首页捕新上限（已废弃）" hint="旧参数，请改用「扫新帖页数」">
              <input
                type="number"
                min={1}
                max={100}
                value={draft.web_crawler_list_head_pages ?? 50}
                onChange={(e) => setNum('web_crawler_list_head_pages', e.target.value)}
              />
            </Field>
            <Field label="列表页总上限" hint="硬上限；填 0 表示不限，翻到没内容为止">
              <input type="number" min={0} max={50000} value={draft.web_crawler_max_list_pages} onChange={(e) => setNum('web_crawler_max_list_pages', e.target.value)} />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">④</span>
            <div>
              <h4>抓帖</h4>
              <p className="field-hint">打开帖子读内容。遇到广告/验证页会自动用浏览器再打开一次。</p>
            </div>
          </div>
          <div className="settings-grid-2 forum-config-grid">
            <Field label="单帖超时（秒）" hint="抓一篇帖最多等多久；0 表示不限制，默认 120">
              <input type="number" min={0} max={900} value={draft.web_crawler_thread_timeout} onChange={(e) => setNum('web_crawler_thread_timeout', e.target.value)} />
            </Field>
            <Field label="取页方式" hint="固定策略，不能改">
              <input type="text" value="列表用浏览器 · 帖子用普通请求 · 广告页再用浏览器" readOnly disabled />
            </Field>
          </div>
        </section>

        <section className="forum-modal-block forum-config-step">
          <div className="forum-config-step-head">
            <span className="forum-config-step-badge">⑤</span>
            <div>
              <h4>入库</h4>
              <p className="field-hint">有下载链就正常入库；没有就只记一条占位。跳过/失败的不算入库。</p>
            </div>
          </div>
          <div className="forum-config-grid forum-config-grid--single">
            <label className="forum-field-block forum-field-block--switch">
              <span className="forum-field-label">每帖只入一条主资源</span>
              <div className="forum-field-control">
                <input type="checkbox" checked disabled title="固定开启，不可关闭" />
              </div>
              <small className="field-hint">帖里其他链接会一并记在 links 里</small>
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
  /** 弹窗打开期间从爬虫状态轮询，避免板块列表游标停在打开瞬间 */
  const [liveCursors, setLiveCursors] = useState<Record<string, number>>(
    () => ({ ...(forum.crawler_config.board_list_cursors || {}) }),
  )

  useEffect(() => {
    setDraft({ ...forum.crawler_config })
    setLiveCursors({ ...(forum.crawler_config.board_list_cursors || {}) })
  }, [forum])

  /** 锁住下层滚动/触摸，避免 iOS 穿透到底栏与设置页 */
  useEffect(() => {
    const html = document.documentElement
    const body = document.body
    const prevHtmlOverflow = html.style.overflow
    const prevBodyOverflow = body.style.overflow
    const scrollY = window.scrollY
    html.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    body.classList.add('modal-open')

    const blockUnderlyingTouch = (e: TouchEvent) => {
      const target = e.target as Element | null
      if (target?.closest?.('.forum-modal-panel')) return
      e.preventDefault()
    }
    document.addEventListener('touchmove', blockUnderlyingTouch, { passive: false })

    return () => {
      html.style.overflow = prevHtmlOverflow
      body.style.overflow = prevBodyOverflow
      body.classList.remove('modal-open')
      document.removeEventListener('touchmove', blockUnderlyingTouch)
      window.scrollTo(0, scrollY)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    const pull = async () => {
      try {
        const st = await fetchCrawlerStatus()
        if (cancelled) return
        if (st.forum_id && st.forum_id !== forum.id) return
        setLiveCursors({ ...(st.board_list_cursors || {}) })
      } catch {
        /* 静默：配置弹窗不必因状态接口失败弹 toast */
      }
    }
    void pull()
    const timer = window.setInterval(() => {
      void pull()
    }, 2000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [forum.id])

  const isEnabled = activeForumId === forum.id
  const boards = useMemo(() => {
    const list = [...(forum.boards || [])]
    const order = forum.crawler_config.board_order || []
    if (!order.length) {
      return list.sort((a, b) => (a.priority ?? 50) - (b.priority ?? 50))
    }
    const byKey = new Map(list.map((b) => [boardUnitKey(b), b]))
    const sorted: ForumBoard[] = []
    for (const id of order) {
      const board = byKey.get(String(id))
      if (board) {
        sorted.push(board)
        byKey.delete(String(id))
      }
    }
    for (const board of byKey.values()) sorted.push(board)
    return sorted
  }, [forum.boards, forum.crawler_config.board_order])

  const activeBoardFid =
    draft.active_board_fid ||
    forum.crawler_config.active_board_fid ||
    (boards[0] ? boardUnitKey(boards[0]) : '')
  const enabledBoardFids = useMemo(() => {
    const raw = draft.enabled_board_fids?.length
      ? draft.enabled_board_fids
      : forum.crawler_config.enabled_board_fids?.length
        ? forum.crawler_config.enabled_board_fids
        : activeBoardFid
          ? [activeBoardFid]
          : []
    const order = draft.board_order || forum.crawler_config.board_order || boards.map((b) => boardUnitKey(b))
    const wanted = new Set(raw.map(String))
    return order.map(String).filter((fid) => wanted.has(fid))
  }, [
    draft.enabled_board_fids,
    draft.board_order,
    forum.crawler_config.enabled_board_fids,
    forum.crawler_config.board_order,
    activeBoardFid,
    boards,
  ])

  const handleToggleBoard = (fid: string, enabled: boolean) => {
    const wanted = new Set(enabledBoardFids)
    if (enabled) wanted.add(fid)
    else wanted.delete(fid)
    if (!wanted.size) {
      toast.info('至少保留一个启用板块')
      return
    }
    const order = draft.board_order || forum.crawler_config.board_order || boards.map((b) => boardUnitKey(b))
    const nextEnabled = order.map(String).filter((id) => wanted.has(id))
    const nextActive = nextEnabled.includes(activeBoardFid) ? activeBoardFid : nextEnabled[0]
    const next = {
      ...draft,
      enabled_board_fids: nextEnabled,
      active_board_fid: nextActive,
      web_crawler_max_boards_per_run: Math.max(1, nextEnabled.length),
    }
    setDraft(next)
    onActiveBoardChange(next)
    void saveForumConfig(forum.id, next).then(
      (res) => onActiveBoardChange({ ...next, ...res.config }),
      (err) => toast.error(err instanceof Error ? err.message : '更新启用板块失败'),
    )
  }

  const handleToggleMany = (fids: string[], enabled: boolean) => {
    const wanted = new Set(enabledBoardFids)
    for (const fid of fids) {
      if (enabled) wanted.add(fid)
      else wanted.delete(fid)
    }
    if (!wanted.size) {
      toast.info('至少保留一个启用板块')
      return
    }
    const order = draft.board_order || forum.crawler_config.board_order || boards.map((b) => boardUnitKey(b))
    const nextEnabled = order.map(String).filter((id) => wanted.has(id))
    const nextActive = nextEnabled.includes(activeBoardFid) ? activeBoardFid : nextEnabled[0]
    const next = {
      ...draft,
      enabled_board_fids: nextEnabled,
      active_board_fid: nextActive,
      web_crawler_max_boards_per_run: Math.max(1, nextEnabled.length),
    }
    setDraft(next)
    onActiveBoardChange(next)
    void saveForumConfig(forum.id, next).then(
      (res) => onActiveBoardChange({ ...next, ...res.config }),
      (err) => toast.error(err instanceof Error ? err.message : '更新启用板块失败'),
    )
  }

  const handleSetCurrentBoard = (fid: string) => {
    if (fid === activeBoardFid) return
    if (!enabledBoardFids.includes(fid)) {
      toast.info('请先勾选启用该板块')
      return
    }
    const next = {
      ...draft,
      active_board_fid: fid,
      enabled_board_fids: enabledBoardFids,
      web_crawler_max_boards_per_run: Math.max(1, enabledBoardFids.length),
    }
    setDraft(next)
    onActiveBoardChange(next)
    void setActiveBoard(forum.id, fid).then(
      (res) => onActiveBoardChange({ ...next, ...res.config }),
      () => {
        /* 失败时保留本地选中，下次保存配置时一并写回 */
      },
    )
  }

  const handleClearCursor = (fid: string) => {
    void clearBoardCursor(forum.id, fid).then(
      (res) => {
        const next = { ...draft, ...res.config }
        setDraft(next)
        setLiveCursors({ ...(res.config.board_list_cursors || {}) })
        onActiveBoardChange(next)
        toast.success(`已清除游标 · ${fid} · 下次深扫从 P1 起`)
      },
      (err) => toast.error(err instanceof Error ? err.message : '清除游标失败'),
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload: ForumCrawlerConfig = {
        ...draft,
        active_board_fid: draft.active_board_fid || activeBoardFid,
        enabled_board_fids: enabledBoardFids,
        web_crawler_interval_minutes: 0,
        web_crawler_max_boards_per_run: Math.max(1, enabledBoardFids.length),
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
    return createPortal(
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
      </div>,
      document.body,
    )
  }

  return createPortal(
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
                  enabledFids={enabledBoardFids}
                  activeBoardFid={activeBoardFid}
                  cursors={liveCursors}
                  onToggle={handleToggleBoard}
                  onToggleMany={handleToggleMany}
                  onSetCurrent={handleSetCurrentBoard}
                  onClearCursor={handleClearCursor}
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
    </div>,
    document.body,
  )
}
