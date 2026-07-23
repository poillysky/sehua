import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchImportSpec, importText, uploadPreviewImages, type ImportSpec } from '../api/importApi'
import {
  buildBoardFacetTree,
  deleteResourcesBatch,
  fetchRecentResources,
  fetchResourceIds,
  mapApiResource,
  PAGE_SIZE,
  recrawlResourcesBatch,
  splitBoardParentChild,
  type ResourceFacets,
  type ResourceRow,
} from '../api/resources'
import { confirmDialog } from '../ui/confirm'
import { toast } from '../ui/toast'
import { formatBoardDescription } from '../utils/boardDescription'

const RESULT_LABEL: Record<ResourceRow['result'], string> = {
  magnet: '磁力',
  ed2k: 'ED2K',
  '115share': '115分享',
  stub: '占位',
  failed: '失败',
}

const EMPTY_FACETS: ResourceFacets = {
  sources: { all: 0, web: 0, upload: 0, telegram: 0 },
  boards: [],
  results: { all: 0, magnet: 0, ed2k: 0, '115share': 0, stub: 0, failed: 0 },
}

type CheckedMeta = {
  hash: string
  sourceUrl?: string
  title: string
  result: ResourceRow['result']
}

export function ResourcesPage() {
  const [items, setItems] = useState<ResourceRow[]>([])
  const [boards, setBoards] = useState<string[]>([])
  const [facets, setFacets] = useState<ResourceFacets>(EMPTY_FACETS)
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [qInput, setQInput] = useState('')
  const [q, setQ] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [detailOpen, setDetailOpen] = useState(false)
  const [checkedIds, setCheckedIds] = useState<string[]>([])
  const [checkedMeta, setCheckedMeta] = useState<Record<string, CheckedMeta>>({})
  const [selectAllBusy, setSelectAllBusy] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [openDims, setOpenDims] = useState({ source: true, board: true, result: true })
  const [expandedBoardParents, setExpandedBoardParents] = useState<Set<string>>(() => new Set())
  const [source, setSource] = useState<'all' | 'web' | 'upload'>('all')
  const [board, setBoard] = useState('all')
  const [result, setResult] = useState<'all' | 'magnet' | 'ed2k' | '115share' | 'stub' | 'failed'>('all')
  const [importOpen, setImportOpen] = useState(false)
  const [recrawlBusy, setRecrawlBusy] = useState(false)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [filterBtnHidden, setFilterBtnHidden] = useState(false)
  const reqSeq = useRef(0)
  const hasLoaded = useRef(false)
  const tableScrollRef = useRef<HTMLDivElement>(null)
  const lastScrollTop = useRef(0)

  const load = useCallback(
    async (opts?: { silent?: boolean; pageOverride?: number }) => {
      const silent = Boolean(opts?.silent && hasLoaded.current)
      const pageNo = opts?.pageOverride ?? page
      const seq = ++reqSeq.current

      if (silent) setRefreshing(true)
      else setLoading(true)

      try {
        const data = await fetchRecentResources({
          page: pageNo,
          pageSize: PAGE_SIZE,
          source,
          board,
          result,
          q,
        })
        if (seq !== reqSeq.current) return

        const rows = data.items.map(mapApiResource)
        const totalCount = Number(data.total ?? data.count ?? rows.length) || 0
        const pageCount = Number(data.pages) || Math.max(1, Math.ceil(totalCount / PAGE_SIZE) || 1)
        const nextFacets: ResourceFacets = data.facets
          ? {
              sources: { ...EMPTY_FACETS.sources, ...(data.facets.sources || {}) },
              boards: data.facets.boards || [],
              results: { ...EMPTY_FACETS.results, ...(data.facets.results || {}) },
            }
          : {
              ...EMPTY_FACETS,
              boards: (data.boards || []).map((name) => ({ name, count: 0 })),
              sources: { ...EMPTY_FACETS.sources, all: totalCount },
              results: { ...EMPTY_FACETS.results, all: totalCount },
            }
        const boardNames =
          nextFacets.boards.length > 0
            ? nextFacets.boards.map((b) => b.name)
            : data.boards || []
        startTransition(() => {
          setItems(rows)
          setTotal(totalCount)
          setPages(pageCount)
          setFacets(nextFacets)
          setBoards(boardNames)
          setSelectedId((prev) => {
            if (prev && rows.some((r) => r.id === prev)) return prev
            return ''
          })
          // 跨页勾选：保留已选；本页行刷新已选 meta
          setCheckedMeta((prev) => {
            let changed = false
            const next = { ...prev }
            for (const r of rows) {
              if (!prev[r.id] || !r.hash) continue
              const meta: CheckedMeta = {
                hash: r.hash,
                sourceUrl: r.sourceUrl,
                title: r.title,
                result: r.result,
              }
              const old = prev[r.id]
              if (
                old.hash !== meta.hash ||
                old.sourceUrl !== meta.sourceUrl ||
                old.title !== meta.title ||
                old.result !== meta.result
              ) {
                next[r.id] = meta
                changed = true
              }
            }
            return changed ? next : prev
          })
        })
        hasLoaded.current = true
      } catch (err) {
        if (seq !== reqSeq.current) return
        toast.error(err instanceof Error ? err.message : '加载失败')
        if (!silent) setItems([])
      } finally {
        if (seq === reqSeq.current) {
          setLoading(false)
          setRefreshing(false)
        }
      }
    },
    [page, source, board, result, q],
  )

  // 打开页面 / 参数变化时自动刷新
  useEffect(() => {
    void load()
  }, [load])

  // 筛选条件变化：清空跨页勾选
  useEffect(() => {
    setCheckedIds([])
    setCheckedMeta({})
  }, [source, board, result, q])

  // 搜索防抖，避免输入卡顿
  useEffect(() => {
    const t = window.setTimeout(() => {
      setPage(1)
      setQ(qInput)
    }, 280)
    return () => window.clearTimeout(t)
  }, [qInput])

  // 回到前台时轻量刷新
  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === 'visible') void load({ silent: true })
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [load])

  // 手机端列表下滑时收起「筛选」按钮，回顶/上滑再显示
  useEffect(() => {
    const el = tableScrollRef.current
    if (!el) return

    function onScroll() {
      if (!window.matchMedia('(max-width: 768px)').matches) {
        setFilterBtnHidden(false)
        return
      }
      const top = el!.scrollTop
      const delta = top - lastScrollTop.current
      lastScrollTop.current = top
      if (top < 24) {
        setFilterBtnHidden(false)
        return
      }
      if (delta > 6) setFilterBtnHidden(true)
      else if (delta < -6) setFilterBtnHidden(false)
    }

    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  const selected = items.find((r) => r.id === selectedId) ?? null
  const checkedRows = useMemo(() => {
    return checkedIds.map((id) => {
      const onPage = items.find((r) => r.id === id)
      if (onPage) return onPage
      const meta = checkedMeta[id]
      if (!meta) {
        return {
          id,
          title: id,
          board: '—',
          outcome: '',
          result: 'failed' as const,
          time: '—',
        }
      }
      return {
        id,
        title: meta.title,
        board: '—',
        outcome: '',
        result: meta.result,
        time: '—',
        hash: meta.hash,
        sourceUrl: meta.sourceUrl,
      }
    })
  }, [checkedIds, checkedMeta, items])
  const recrawlableChecked = checkedRows.filter((r) => r.sourceUrl && r.hash)
  const deletableChecked = checkedRows.filter((r) => Boolean(r.hash))
  const allPageChecked = items.length > 0 && items.every((r) => checkedIds.includes(r.id))
  const somePageChecked = items.some((r) => checkedIds.includes(r.id))
  const allFilteredSelected =
    total > 0 && checkedIds.length > 0 && checkedIds.length >= total
  const rowOffset = (page - 1) * PAGE_SIZE
  const busy = loading || refreshing || recrawlBusy || deleteBusy || selectAllBusy

  function metaFromRow(r: ResourceRow): CheckedMeta | null {
    if (!r.hash) return null
    return {
      hash: r.hash,
      sourceUrl: r.sourceUrl,
      title: r.title,
      result: r.result,
    }
  }

  function toggleChecked(id: string, next?: boolean) {
    const row = items.find((r) => r.id === id)
    const willOn = next ?? !checkedIds.includes(id)
    setCheckedIds((prev) => {
      if (willOn) return prev.includes(id) ? prev : [...prev, id]
      return prev.filter((x) => x !== id)
    })
    setCheckedMeta((prev) => {
      if (!willOn) {
        if (!(id in prev)) return prev
        const copy = { ...prev }
        delete copy[id]
        return copy
      }
      const meta = row ? metaFromRow(row) : prev[id]
      if (!meta) return prev
      return { ...prev, [id]: meta }
    })
  }

  function toggleCheckAllPage() {
    if (allPageChecked) {
      const pageIds = new Set(items.map((r) => r.id))
      setCheckedIds((prev) => prev.filter((id) => !pageIds.has(id)))
      setCheckedMeta((prev) => {
        const next = { ...prev }
        for (const id of pageIds) delete next[id]
        return next
      })
      return
    }
    setCheckedIds((prev) => {
      const set = new Set(prev)
      for (const r of items) set.add(r.id)
      return [...set]
    })
    setCheckedMeta((prev) => {
      const next = { ...prev }
      for (const r of items) {
        const meta = metaFromRow(r)
        if (meta) next[r.id] = meta
      }
      return next
    })
  }

  const onSelectAllFiltered = async () => {
    if (busy) return
    if (total <= 0) {
      toast.info('当前筛选下没有可选项')
      return
    }
    if (allFilteredSelected) {
      setCheckedIds([])
      setCheckedMeta({})
      toast.info('已取消全选')
      return
    }
    setSelectAllBusy(true)
    try {
      const res = await fetchResourceIds({
        source,
        board,
        result,
        q: q || undefined,
        limit: 2000,
      })
      const nextIds: string[] = []
      const nextMeta: Record<string, CheckedMeta> = {}
      for (const it of res.items || []) {
        const id = String(it.id)
        const hash = (it.hash || '').trim()
        if (!id || !hash) continue
        nextIds.push(id)
        const kind = (['magnet', 'ed2k', '115share', 'stub', 'failed'].includes(String(it.link_kind))
          ? it.link_kind
          : 'failed') as ResourceRow['result']
        nextMeta[id] = {
          hash,
          sourceUrl: it.source_url || undefined,
          title: (it.title || hash).trim() || hash,
          result: kind,
        }
      }
      setCheckedIds(nextIds)
      setCheckedMeta(nextMeta)
      if (!nextIds.length) {
        toast.info('当前筛选下没有有效条目')
      } else if (res.truncated) {
        toast.info(`已选前 ${nextIds.length} 条（共 ${res.total}，单次上限 ${res.limit}）`)
      } else {
        toast.success(`已全选当前筛选 ${nextIds.length} 条`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '全选筛选失败')
    } finally {
      setSelectAllBusy(false)
    }
  }

  function closeFilterIfMobile() {
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches) {
      setFilterOpen(false)
    }
  }

  function changeSource(next: 'all' | 'web' | 'upload') {
    setSource(next)
    if (next !== 'all') {
      setBoard('all')
      setResult('all')
    }
    setPage(1)
    closeFilterIfMobile()
  }

  function changeBoard(next: string) {
    setBoard(next)
    if (next !== 'all') {
      setSource('all')
      setResult('all')
    }
    setPage(1)
    closeFilterIfMobile()
  }

  function changeResult(next: 'all' | 'magnet' | 'ed2k' | '115share' | 'stub' | 'failed') {
    setResult(next)
    if (next !== 'all') {
      setSource('all')
      setBoard('all')
    }
    setPage(1)
    closeFilterIfMobile()
  }

  function goPage(next: number) {
    const p = Math.max(1, Math.min(next, pages))
    setPage(p)
  }

  function toggleDim(key: keyof typeof openDims) {
    setOpenDims((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const boardTree = useMemo(() => {
    const items = facets.boards.length
      ? facets.boards
      : boards.map((name) => ({ name, count: 0 }))
    return buildBoardFacetTree(items)
  }, [facets.boards, boards])

  useEffect(() => {
    if (board === 'all') return
    const { parent } = splitBoardParentChild(board)
    if (!parent) return
    setExpandedBoardParents((prev) => {
      if (prev.has(parent)) return prev
      const next = new Set(prev)
      next.add(parent)
      return next
    })
  }, [board])

  function toggleBoardParent(parent: string) {
    setExpandedBoardParents((prev) => {
      const next = new Set(prev)
      if (next.has(parent)) next.delete(parent)
      else next.add(parent)
      return next
    })
  }

  const onRecrawlSelected = async () => {
    // 优先批量勾选；未勾选时回退到当前高亮行
    let targets = recrawlableChecked
    if (targets.length === 0 && selected?.sourceUrl && selected.hash) {
      targets = [selected]
    }
    if (targets.length === 0) {
      if (checkedRows.length > 0) {
        toast.warn('勾选的条目均无来源帖链接，无法重爬')
      } else {
        toast.info('请先勾选要重爬的资源')
      }
      return
    }
    const skipped = checkedRows.length - recrawlableChecked.length
    const preview = targets
      .slice(0, 5)
      .map((r) => r.title)
      .join('\n')
    const more = targets.length > 5 ? `\n…另有 ${targets.length - 5} 条` : ''
    const ok = await confirmDialog({
      title: '批量已入库重爬',
      message:
        `将对 ${targets.length} 条重新抓取并按 hash 覆盖更新` +
        (skipped > 0 ? `（跳过无来源链接 ${skipped} 条）` : '') +
        `：\n${preview}${more}`,
      confirmText: targets.length > 1 ? `重爬 ${targets.length} 条` : '开始重爬',
    })
    if (!ok) return
    setRecrawlBusy(true)
    try {
      const hashes = targets.map((r) => r.hash!).filter(Boolean)
      const { result } = await recrawlResourcesBatch(hashes)
      const imported = Number(result.imported || 0)
      const removed = Number(result.removed || 0)
      const queued = Number(result.queued || 0)
      const failed = Number(result.failed || 0)
      if (result.mode === 'queued' && queued > 0) {
        toast.success(
          `已入队 ${queued} 条` + (failed > 0 ? ` · 跳过 ${failed}` : '') + ' · 连续调度将依次抓取入库',
        )
      } else if ((imported > 0 || removed > 0) && failed === 0) {
        const parts = [
          imported > 0 ? `入库 ${imported}` : '',
          removed > 0 ? `删除占位 ${removed}` : '',
        ].filter(Boolean)
        toast.success(`重爬完成 · ${parts.join(' · ')}`)
      } else if (imported > 0 || removed > 0) {
        toast.warn(`重爬结束 · 入库 ${imported} · 删占位 ${removed} · 失败 ${failed}`)
      } else {
        toast.error(result.error || `重爬未入库 · 失败 ${failed || hashes.length}`)
      }
      setCheckedIds([])
      setCheckedMeta({})
      await load({ silent: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '批量重爬失败')
    } finally {
      setRecrawlBusy(false)
    }
  }

  const onDeleteSelected = async () => {
    let targets = deletableChecked
    if (targets.length === 0 && selected?.hash) {
      targets = [selected]
    }
    if (targets.length === 0) {
      if (checkedRows.length > 0) {
        toast.warn('勾选的条目均无 hash，无法删除')
      } else {
        toast.info('请先勾选要删除的资源')
      }
      return
    }
    const skipped = checkedRows.length - deletableChecked.length
    const preview = targets
      .slice(0, 5)
      .map((r) => r.title)
      .join('\n')
    const more = targets.length > 5 ? `\n…另有 ${targets.length - 5} 条` : ''
    const ok = await confirmDialog({
      title: targets.length > 1 ? '批量删除资源' : '删除资源',
      message:
        `确定删除 ${targets.length} 条资源？此操作不可恢复。` +
        (skipped > 0 ? `\n（跳过无 hash ${skipped} 条）` : '') +
        `\n${preview}${more}`,
      confirmText: targets.length > 1 ? `删除 ${targets.length} 条` : '删除该资源',
      danger: true,
    })
    if (!ok) return
    setDeleteBusy(true)
    try {
      const hashes = targets.map((r) => r.hash!).filter(Boolean)
      const result = await deleteResourcesBatch(hashes)
      const deleted = Number(result.deleted || 0)
      const missing = Number(result.missing || 0)
      if (deleted > 0 && missing === 0) {
        toast.success(`已删除 ${deleted} 条`)
      } else if (deleted > 0) {
        toast.warn(`已删除 ${deleted} 条 · 未找到 ${missing} 条`)
      } else {
        toast.error('未删除任何资源（可能已不存在）')
      }
      const removedIds = new Set(targets.map((r) => r.id))
      setCheckedIds((prev) => prev.filter((id) => !removedIds.has(id)))
      setCheckedMeta((prev) => {
        const next = { ...prev }
        for (const id of removedIds) delete next[id]
        return next
      })
      if (selected && removedIds.has(selected.id)) {
        setSelectedId('')
        setDetailOpen(false)
      }
      await load({ silent: true })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeleteBusy(false)
    }
  }

  const sourceCount = facets.sources[source] ?? facets.sources.all ?? 0
  const boardCount =
    board === 'all'
      ? facets.boards.reduce((sum, b) => sum + b.count, 0)
      : facets.boards.find((b) => b.name === board)?.count ?? total
  const boardTotal = facets.boards.reduce((sum, b) => sum + b.count, 0)
  const resultFacets = facets.results || EMPTY_FACETS.results || {}
  const resultCount = resultFacets[result] ?? resultFacets.all ?? 0

  return (
    <section className={`page page-resources active ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className={`filter-sidebar ${filterOpen ? 'open' : ''} ${sidebarCollapsed ? 'is-collapsed' : ''}`}>
        <div className="filter-sidebar-head">
          <span className="filter-sidebar-title">筛选</span>
          <button type="button" className="btn ghost sm mobile-only" onClick={() => setFilterOpen(false)}>
            关闭
          </button>
        </div>

        <div className="filter-panel">
          <div className={`dim-card ${openDims.source ? '' : 'collapsed'}`}>
            <button
              type="button"
              className="dim-head"
              aria-expanded={openDims.source}
              onClick={() => toggleDim('source')}
            >
              <span className="dim-head-label">
                <span className="dim-caret" aria-hidden />
                <span>来源</span>
              </span>
              <span className="dim-count">{sourceCount}</span>
            </button>
            {openDims.source ? (
              <div className="dim-body">
                {(
                  [
                    ['all', '全部'],
                    ['web', '论坛爬取'],
                    ['upload', '人工导入'],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className={source === id ? 'dim-item active' : 'dim-item'}
                    onClick={() => changeSource(id)}
                  >
                    <span className="dim-item-label">{label}</span>
                    <span className="dim-item-count">{facets.sources[id] ?? 0}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          <div className={`dim-card ${openDims.board ? '' : 'collapsed'}`}>
            <button
              type="button"
              className="dim-head"
              aria-expanded={openDims.board}
              onClick={() => toggleDim('board')}
            >
              <span className="dim-head-label">
                <span className="dim-caret" aria-hidden />
                <span>板块</span>
              </span>
              <span className="dim-count">{boardCount}</span>
            </button>
            {openDims.board ? (
              <div className="dim-body">
                <button type="button" className={board === 'all' ? 'dim-item active' : 'dim-item'} onClick={() => changeBoard('all')}>
                  <span className="dim-item-label">全部板块</span>
                  <span className="dim-item-count">{boardTotal}</span>
                </button>
                {boardTree.map((node) => {
                  const open = expandedBoardParents.has(node.parent)
                  const hasKids = Boolean(node.self) || node.children.length > 0
                  const parentActive =
                    board === node.parent ||
                    (node.self && board === node.self.name) ||
                    node.children.some((c) => c.name === board)
                  const onlyParent = !node.children.length && node.self
                  return (
                    <div
                      key={node.parent}
                      className={`dim-board-group${open ? ' is-open' : ''}${parentActive ? ' has-active' : ''}`}
                    >
                      <div className="dim-board-parent-row">
                        {hasKids && !onlyParent ? (
                          <button
                            type="button"
                            className={`dim-board-expand${open ? ' is-open' : ''}`}
                            aria-expanded={open}
                            title={open ? '收起子分类' : '展开子分类'}
                            onClick={() => toggleBoardParent(node.parent)}
                          >
                            <span className="dim-caret" aria-hidden />
                          </button>
                        ) : (
                          <span className="dim-board-expand-spacer" aria-hidden />
                        )}
                        <button
                          type="button"
                          className={
                            board === (node.self?.name || node.parent) && !node.children.some((c) => c.name === board)
                              ? 'dim-item dim-board-parent active'
                              : 'dim-item dim-board-parent'
                          }
                          onClick={() => {
                            if (node.self) changeBoard(node.self.name)
                            else if (onlyParent) changeBoard(node.parent)
                            else toggleBoardParent(node.parent)
                          }}
                          title={
                            node.self
                              ? `筛选：${node.self.name}`
                              : onlyParent
                                ? `筛选：${node.parent}`
                                : '展开查看子分类'
                          }
                        >
                          <span className="dim-item-label">{node.parent}</span>
                          <span className="dim-item-count">{node.total}</span>
                        </button>
                      </div>
                      {open && !onlyParent ? (
                        <div className="dim-board-children">
                          {node.self ? (
                            <button
                              type="button"
                              className={board === node.self.name ? 'dim-item dim-board-child active' : 'dim-item dim-board-child'}
                              onClick={() => changeBoard(node.self!.name)}
                            >
                              <span className="dim-item-label">未分子类</span>
                              <span className="dim-item-count">{node.self.count}</span>
                            </button>
                          ) : null}
                          {node.children.map((c) => (
                            <button
                              key={c.name}
                              type="button"
                              className={board === c.name ? 'dim-item dim-board-child active' : 'dim-item dim-board-child'}
                              onClick={() => changeBoard(c.name)}
                              title={c.name}
                            >
                              <span className="dim-item-label">{c.label}</span>
                              <span className="dim-item-count">{c.count}</span>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>

          <div className={`dim-card ${openDims.result ? '' : 'collapsed'}`}>
            <button
              type="button"
              className="dim-head"
              aria-expanded={openDims.result}
              onClick={() => toggleDim('result')}
            >
              <span className="dim-head-label">
                <span className="dim-caret" aria-hidden />
                <span>最终结果</span>
              </span>
              <span className="dim-count">{resultCount}</span>
            </button>
            {openDims.result ? (
              <div className="dim-body">
                {(
                  [
                    ['all', '全部'],
                    ['magnet', '磁力'],
                    ['ed2k', 'ED2K'],
                    ['115share', '115分享'],
                    ['stub', '占位'],
                    ['failed', '失败'],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    className={result === id ? 'dim-item active' : 'dim-item'}
                    onClick={() => changeResult(id)}
                  >
                    <span className="dim-item-label">{label}</span>
                    <span className="dim-item-count">{resultFacets[id] ?? 0}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div className="filter-actions">
          <button type="button" className="btn primary block btn-import" onClick={() => setImportOpen(true)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span>快速导入</span>
          </button>
        </div>
        <div className="sidebar-foot">
          <span className="foot-version">{busy ? '同步中…' : `共 ${total} 条`}</span>
        </div>
      </aside>

      {filterOpen ? (
        <button type="button" className="drawer-backdrop mobile-only" aria-label="关闭筛选" onClick={() => setFilterOpen(false)} />
      ) : null}

      <div className="split-main">
        <button
          type="button"
          className={`filter-rail-toggle desktop-only ${sidebarCollapsed ? 'is-collapsed' : ''}`}
          title={sidebarCollapsed ? '展开筛选' : '收起筛选'}
          aria-expanded={!sidebarCollapsed}
          aria-label={sidebarCollapsed ? '展开筛选' : '收起筛选'}
          onClick={() => setSidebarCollapsed((v) => !v)}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            {sidebarCollapsed ? <path d="M9 6l6 6-6 6" /> : <path d="M15 6l-6 6 6 6" />}
          </svg>
        </button>
        <div className={`table-pane ${refreshing ? 'is-refreshing' : ''}`}>
          <div className={`table-toolbar${filterBtnHidden ? ' filter-btn-hidden' : ''}`}>
            <button
              type="button"
              className="btn secondary sm mobile-only filter-open-btn"
              onClick={() => setFilterOpen(true)}
            >
              筛选
            </button>
            <input
              type="search"
              placeholder="按名称搜索…"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
            />
            <span className="toolbar-meta">
              {total === 0
                ? '共 0 条'
                : checkedIds.length > 0
                  ? `已选 ${checkedIds.length} · 第 ${rowOffset + 1}–${rowOffset + items.length} 条，共 ${total} 条`
                  : `第 ${rowOffset + 1}–${rowOffset + items.length} 条，共 ${total} 条`}
            </span>
            <button
              type="button"
              className="btn secondary sm"
              disabled={busy || total <= 0}
              title={
                allFilteredSelected
                  ? '取消当前筛选下的全选'
                  : `按当前筛选（来源/板块/结果/搜索）全选全部页，共约 ${total} 条`
              }
              onClick={() => void onSelectAllFiltered()}
            >
              {selectAllBusy
                ? '全选中…'
                : allFilteredSelected
                  ? `已全选 ${checkedIds.length}`
                  : `全选筛选${total > 0 ? ` ${total}` : ''}`}
            </button>
            <button
              type="button"
              className="btn secondary sm"
              disabled={
                busy ||
                recrawlBusy ||
                deleteBusy ||
                (recrawlableChecked.length === 0 && !(selected?.sourceUrl && selected.hash))
              }
              title={
                recrawlableChecked.length > 0
                  ? `重爬已勾选 ${recrawlableChecked.length} 条（有来源帖）`
                  : selected?.sourceUrl
                    ? '重爬当前高亮行'
                    : '请先勾选要重爬的资源'
              }
              onClick={() => void onRecrawlSelected()}
            >
              {recrawlBusy
                ? '重爬中…'
                : recrawlableChecked.length > 1
                  ? `重爬选中 ${recrawlableChecked.length}`
                  : '重爬选中'}
            </button>
            <button
              type="button"
              className="btn danger sm"
              disabled={
                busy ||
                recrawlBusy ||
                deleteBusy ||
                (deletableChecked.length === 0 && !selected?.hash)
              }
              title={
                deletableChecked.length > 0
                  ? `删除已勾选 ${deletableChecked.length} 条`
                  : selected?.hash
                    ? '删除当前高亮行'
                    : '请先勾选要删除的资源'
              }
              onClick={() => void onDeleteSelected()}
            >
              {deleteBusy
                ? '删除中…'
                : deletableChecked.length > 1
                  ? `删除选中 ${deletableChecked.length}`
                  : '删除选中'}
            </button>
            <button type="button" className="btn secondary sm" onClick={() => void load({ silent: true })} disabled={busy || recrawlBusy || deleteBusy}>
              {refreshing ? '刷新中' : '刷新'}
            </button>
          </div>
          <div className="table-scroll" ref={tableScrollRef}>
            <table className="resource-table">
              <thead>
                <tr>
                  <th className="col-check">
                    <label
                      className="row-check"
                      title={
                        allPageChecked
                          ? '取消本页全选'
                          : '仅全选本页；跨页请用「全选筛选」'
                      }
                    >
                      <input
                        type="checkbox"
                        checked={allPageChecked}
                        ref={(el) => {
                          if (el) el.indeterminate = !allPageChecked && somePageChecked
                        }}
                        disabled={items.length === 0 || busy}
                        onChange={() => toggleCheckAllPage()}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </label>
                  </th>
                  <th className="col-icon">#</th>
                  <th className="col-name">帖子</th>
                  <th className="col-board">论坛 / 板块·分类</th>
                  <th className="col-outcome">判定</th>
                  <th className="col-result">结果</th>
                  <th className="col-time">处理时间</th>
                </tr>
              </thead>
              <tbody>
                {loading && items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty">
                      加载中...
                    </td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty">
                      暂无资源，解析入库后将显示在此
                    </td>
                  </tr>
                ) : (
                  items.map((r, i) => {
                    const isChecked = checkedIds.includes(r.id)
                    return (
                      <tr
                        key={r.id}
                        className={
                          (selected?.id === r.id ? 'resource-row selected' : 'resource-row') +
                          (isChecked ? ' is-checked' : '')
                        }
                        onClick={() => {
                          if (selectedId === r.id && detailOpen) {
                            setDetailOpen(false)
                            return
                          }
                          setSelectedId(r.id)
                          setDetailOpen(true)
                        }}
                      >
                        <td className="col-check" onClick={(e) => e.stopPropagation()}>
                          <label className="row-check">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(e) => toggleChecked(r.id, e.target.checked)}
                            />
                          </label>
                        </td>
                        <td className="col-icon">{rowOffset + i + 1}</td>
                        <td className="col-name" title={r.title}>
                          <span className="row-title">{r.title}</span>
                        </td>
                        <td className="col-board" title={[r.forum, r.board].filter(Boolean).join(' · ')}>
                          {r.forum ? (
                            <>
                              <span className="row-forum">{r.forum}</span>
                              <span className="row-forum-sep"> · </span>
                            </>
                          ) : null}
                          {r.board}
                        </td>
                        <td className="col-outcome" title={r.outcome}>
                          {r.outcome}
                        </td>
                        <td className="col-result">
                          <span className={`tag tag-${r.result}`}>{RESULT_LABEL[r.result]}</span>
                        </td>
                        <td className="col-time">{r.time}</td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="pager-bar">
            <span className="pager-info">
              第 {page} 页，共 {pages} 页，每页 {PAGE_SIZE} 条
            </span>
            <div className="pager-actions">
              <button type="button" className="btn secondary sm" disabled={page <= 1 || busy} onClick={() => goPage(1)}>
                首页
              </button>
              <button type="button" className="btn secondary sm" disabled={page <= 1 || busy} onClick={() => goPage(page - 1)}>
                上一页
              </button>
              <button type="button" className="btn secondary sm" disabled={page >= pages || busy} onClick={() => goPage(page + 1)}>
                下一页
              </button>
              <button type="button" className="btn secondary sm" disabled={page >= pages || busy} onClick={() => goPage(pages)}>
                末页
              </button>
            </div>
          </div>
        </div>

        <div className={`detail-pane${detailOpen && selected ? ' is-open' : ''}`}>
          <DetailTabs
            row={selected}
            recrawlBusy={recrawlBusy}
            deleteBusy={deleteBusy}
            onRecrawl={() => void onRecrawlSelected()}
            onDelete={() => void onDeleteSelected()}
            onCollapse={() => setDetailOpen(false)}
          />
        </div>
      </div>

      {importOpen ? (
        <QuickImportModal
          onClose={() => setImportOpen(false)}
          onImported={() => {
            setImportOpen(false)
            void load({ silent: true })
          }}
        />
      ) : null}
    </section>
  )
}

function QuickImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [spec, setSpec] = useState<ImportSpec | null>(null)
  const [title, setTitle] = useState('')
  const [fileSize, setFileSize] = useState('')
  const [previewImages, setPreviewImages] = useState<string[]>([])
  const [previewUrlDraft, setPreviewUrlDraft] = useState('')
  const [forumName, setForumName] = useState('色花堂')
  const [boardName, setBoardName] = useState('')
  const [links, setLinks] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [extractPassword, setExtractPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [resultHint, setResultHint] = useState('')

  useEffect(() => {
    void fetchImportSpec()
      .then(setSpec)
      .catch((err) => toast.error(err instanceof Error ? err.message : '加载导入标准失败'))
  }, [])

  const buildMeta = () => {
    const sizeRaw = fileSize.trim().replace(/,/g, '')
    const sizeNum = sizeRaw && /^\d+$/.test(sizeRaw) ? Number(sizeRaw) : null
    return {
      title: title.trim() || undefined,
      file_size: sizeNum && sizeNum > 0 ? sizeNum : null,
      preview_images: previewImages.slice(0, 5),
      forum_name: forumName.trim() || undefined,
      board_name: boardName.trim() || undefined,
      source_url: sourceUrl.trim() || undefined,
      extract_password: extractPassword.trim() || undefined,
    }
  }

  const addPreviewUrl = () => {
    const url = previewUrlDraft.trim()
    if (!url) return
    if (previewImages.length >= 5) {
      toast.warn('预览图最多 5 张')
      return
    }
    if (previewImages.includes(url)) {
      toast.warn('该预览图已添加')
      return
    }
    setPreviewImages((prev) => [...prev, url].slice(0, 5))
    setPreviewUrlDraft('')
  }

  const onUploadPreviews = async (fileList: FileList | null) => {
    if (!fileList?.length) return
    const room = 5 - previewImages.length
    if (room <= 0) {
      toast.warn('预览图最多 5 张')
      return
    }
    const files = Array.from(fileList).slice(0, room)
    setUploading(true)
    try {
      const urls = await uploadPreviewImages(files)
      setPreviewImages((prev) => {
        const next = [...prev]
        for (const u of urls) {
          if (!next.includes(u) && next.length < 5) next.push(u)
        }
        return next
      })
      toast.success(`已上传 ${urls.length} 张预览图`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '预览图上传失败')
    } finally {
      setUploading(false)
    }
  }

  const onSubmit = async () => {
    if (!links.trim()) {
      toast.warn('请填写第 6 项：magnet 或 ED2K 链接')
      return
    }
    setBusy(true)
    setResultHint('')
    try {
      const res = await importText({ links: links.trim(), ...buildMeta() })
      const msg =
        `成功导入 ${res.count} 条` +
        (res.ed2k || res.magnets ? `（ED2K ${res.ed2k ?? 0} · magnet ${res.magnets ?? 0}）` : '')
      setResultHint(msg)
      toast.success(msg)
      onImported()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '导入失败')
    } finally {
      setBusy(false)
    }
  }

  const onFillLinksFromFile = async (file: File | null) => {
    if (!file) return
    try {
      const text = await file.text()
      setLinks((prev) => (prev.trim() ? `${prev.trim()}\n${text.trim()}` : text.trim()))
      toast.info('已填入链接区，请核对其他字段后点导入')
    } catch {
      toast.error('读取文件失败')
    }
  }

  return (
    <div className="modal-backdrop import-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-card card import-modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-import-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head import-modal-head">
          <div>
            <h3 id="quick-import-title">快速导入</h3>
            <p className="import-modal-sub">统一入库格式 · 第 6 项链接必填</p>
          </div>
          <button type="button" className="btn ghost sm icon-only" title="关闭" disabled={busy} onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="modal-body import-modal-body import-modal-body--form">
          <ol className="import-form-list">
            <li className="import-form-item">
              <label className="import-form-label" htmlFor="qi-title">
                <span className="resource-format-no">1</span>
                <span>
                  <strong>标题</strong>
                  <small>可选；空则用链接内文件名</small>
                </span>
              </label>
              <input
                id="qi-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="资源标题"
              />
            </li>

            <li className="import-form-item">
              <label className="import-form-label" htmlFor="qi-size">
                <span className="resource-format-no">2</span>
                <span>
                  <strong>文件大小</strong>
                  <small>字节数；空则用链接内大小</small>
                </span>
              </label>
              <input
                id="qi-size"
                type="text"
                inputMode="numeric"
                value={fileSize}
                onChange={(e) => setFileSize(e.target.value)}
                placeholder="例如 2147483648"
              />
            </li>

            <li className="import-form-item">
              <div className="import-form-label">
                <span className="resource-format-no">3</span>
                <span>
                  <strong>预览图</strong>
                  <small>最多 5 张 · 可本地上传或粘贴 URL</small>
                </span>
              </div>
              {previewImages.length ? (
                <ul className="import-preview-grid">
                  {previewImages.map((url) => (
                    <li key={url} className="import-preview-thumb">
                      <img src={url} alt="" />
                      <button
                        type="button"
                        className="import-preview-remove"
                        title="移除"
                        onClick={() => setPreviewImages((prev) => prev.filter((u) => u !== url))}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="hint import-preview-empty">尚未添加预览图</p>
              )}
              <div className="import-preview-tools">
                <label className={`btn secondary sm import-file-btn ${uploading || previewImages.length >= 5 ? 'is-disabled' : ''}`}>
                  {uploading ? '上传中…' : '上传图片'}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp,.gif"
                    multiple
                    hidden
                    disabled={busy || uploading || previewImages.length >= 5}
                    onChange={(e) => {
                      void onUploadPreviews(e.target.files)
                      e.target.value = ''
                    }}
                  />
                </label>
                <div className="import-preview-url-row">
                  <input
                    type="text"
                    value={previewUrlDraft}
                    onChange={(e) => setPreviewUrlDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addPreviewUrl()
                      }
                    }}
                    placeholder="或粘贴图片 URL 后添加"
                    disabled={previewImages.length >= 5}
                  />
                  <button
                    type="button"
                    className="btn ghost sm"
                    disabled={!previewUrlDraft.trim() || previewImages.length >= 5}
                    onClick={addPreviewUrl}
                  >
                    添加
                  </button>
                </div>
              </div>
            </li>

            <li className="import-form-item">
              <label className="import-form-label" htmlFor="qi-forum">
                <span className="resource-format-no">4</span>
                <strong>来源论坛名</strong>
              </label>
              <input
                id="qi-forum"
                type="text"
                value={forumName}
                onChange={(e) => setForumName(e.target.value)}
                placeholder="色花堂"
              />
            </li>

            <li className="import-form-item">
              <label className="import-form-label" htmlFor="qi-board">
                <span className="resource-format-no">5</span>
                <strong>来源板块名</strong>
              </label>
              <input
                id="qi-board"
                type="text"
                value={boardName}
                onChange={(e) => setBoardName(e.target.value)}
                placeholder="如：亚洲无码原创"
              />
            </li>

            <li className="import-form-item import-form-item--required">
              <label className="import-form-label" htmlFor="qi-links">
                <span className="resource-format-no">6</span>
                <span>
                  <strong>magnet 或 ED2K 链接</strong>
                  <small>必填 · 可多行</small>
                </span>
              </label>
              <textarea
                id="qi-links"
                rows={6}
                className="import-textarea"
                spellCheck={false}
                value={links}
                onChange={(e) => setLinks(e.target.value)}
                placeholder={spec?.example || 'ed2k://|file|…|/ 或 magnet:?xt=urn:btih:…'}
              />
              <div className="import-links-tools">
                <code className="import-code">{spec?.ed2k_format || 'ed2k://|file|<名>|<大小>|<hash>|/'}</code>
                <label className="btn ghost sm import-file-btn">
                  从 txt 填入
                  <input
                    type="file"
                    accept=".txt,.text,text/plain"
                    hidden
                    disabled={busy}
                    onChange={(e) => void onFillLinksFromFile(e.target.files?.[0] || null)}
                  />
                </label>
              </div>
            </li>

            <li className="import-form-item">
              <label className="import-form-label" htmlFor="qi-source">
                <span className="resource-format-no">7</span>
                <strong>帖子原链接</strong>
              </label>
              <input
                id="qi-source"
                type="text"
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="https://www.sehuatang.net/thread-…html"
              />
            </li>

            <li className="import-form-item">
              <label className="import-form-label" htmlFor="qi-pwd">
                <span className="resource-format-no">8</span>
                <span>
                  <strong>资源解压密码</strong>
                  <small>无则留空</small>
                </span>
              </label>
              <input
                id="qi-pwd"
                type="text"
                value={extractPassword}
                onChange={(e) => setExtractPassword(e.target.value)}
                placeholder="解压密码"
              />
            </li>
          </ol>

          <div className="modal-actions import-modal-actions">
            <button type="button" className="btn ghost sm" disabled={busy} onClick={onClose}>
              取消
            </button>
            <button type="button" className="btn primary sm" disabled={busy || uploading} onClick={() => void onSubmit()}>
              {busy ? '导入中…' : '导入入库'}
            </button>
          </div>
          {resultHint ? <p className="hint import-result">{resultHint}</p> : null}
        </div>
      </div>
    </div>
  )
}

function isLikelyPreviewUrl(url: string): boolean {
  const u = (url || '').trim()
  if (!/^https?:\/\//i.test(u)) return false
  const low = u.toLowerCase()
  if (
    /attachment\/common\/|usergroup_icon|groupicon|static\/image\/|smiley|avatar|uc_server\/|favicon|(?:_icon|icon_)\.(?:gif|png|jpe?g|webp)/.test(
      low,
    )
  ) {
    return false
  }
  return true
}

function DetailPreviewGrid({ urls }: { urls: string[] }) {
  const candidates = urls.filter(isLikelyPreviewUrl)
  const [dead, setDead] = useState<Record<string, boolean>>({})
  const visible = candidates.filter((u) => !dead[u])
  if (visible.length === 0) {
    return <span className="val hint">无预览图</span>
  }
  return (
    <ul className="detail-preview-grid">
      {visible.map((url) => (
        <li key={url}>
          <a href={url} target="_blank" rel="noreferrer">
            <img
              src={url}
              alt=""
              loading="lazy"
              onError={() => setDead((prev) => (prev[url] ? prev : { ...prev, [url]: true }))}
            />
          </a>
        </li>
      ))}
    </ul>
  )
}

function DetailTabs({
  row,
  recrawlBusy,
  deleteBusy,
  onRecrawl,
  onDelete,
  onCollapse,
}: {
  row: ResourceRow | null
  recrawlBusy?: boolean
  deleteBusy?: boolean
  onRecrawl?: () => void
  onDelete?: () => void
  onCollapse?: () => void
}) {
  const [tab, setTab] = useState<'verdict' | 'source' | 'content'>('verdict')

  return (
    <>
      <div className="detail-tabs">
        {(
          [
            ['verdict', '判定'],
            ['source', '来源'],
            ['content', '内容'],
          ] as const
        ).map(([id, label]) => (
          <button key={id} type="button" className={tab === id ? 'detail-tab active' : 'detail-tab'} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
        {onCollapse ? (
          <button
            type="button"
            className="detail-collapse-btn mobile-only"
            title="收起详情"
            aria-label="收起详情"
            onClick={onCollapse}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        ) : null}
      </div>
      <div className="detail-content">
        {!row ? (
          <p className="hint">选择一条记录，核对处理判定是否合理</p>
        ) : tab === 'verdict' ? (
          <div className="detail-grid">
            <div className="detail-field full">
              <span className="lbl">帖子</span>
              <span className="val">{row.title}</span>
            </div>
            <div className="detail-field">
              <span className="lbl">结果</span>
              <span className="val">
                <span className={`tag tag-${row.result}`}>{RESULT_LABEL[row.result]}</span>
              </span>
            </div>
            <div className="detail-field">
              <span className="lbl">判定</span>
              <span className="val">{row.outcome}</span>
            </div>
            <div className="detail-field">
              <span className="lbl">论坛</span>
              <span className="val">{row.forum || '—'}</span>
            </div>
            <div className="detail-field">
              <span className="lbl">板块 / 分类</span>
              <span className="val">{row.board}</span>
            </div>
            <div className="detail-field">
              <span className="lbl">时间</span>
              <span className="val">{row.time}</span>
            </div>
            {row.hash ? (
              <div className="detail-field full">
                <span className="lbl">Hash</span>
                <span className="val mono">{row.hash}</span>
              </div>
            ) : null}
            <div className="detail-field full detail-actions">
              {row.sourceUrl ? (
                <button
                  type="button"
                  className="btn secondary sm"
                  disabled={Boolean(recrawlBusy || deleteBusy)}
                  onClick={() => onRecrawl?.()}
                >
                  {recrawlBusy ? '重爬中…' : '已入库重爬'}
                </button>
              ) : null}
              {row.hash ? (
                <button
                  type="button"
                  className="btn danger sm"
                  disabled={Boolean(recrawlBusy || deleteBusy)}
                  onClick={() => onDelete?.()}
                >
                  {deleteBusy ? '删除中…' : '删除该资源'}
                </button>
              ) : null}
            </div>
          </div>
        ) : tab === 'source' ? (
          <div className="detail-grid">
            <div className="detail-field full">
              <span className="lbl">来源 URL</span>
              {row.sourceUrl ? (
                <a
                  className="val mono detail-source-link"
                  href={row.sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                  title="在新标签打开来源帖"
                >
                  {row.sourceUrl}
                </a>
              ) : (
                <span className="val mono">—</span>
              )}
            </div>
            <div className="detail-field">
              <span className="lbl">来源论坛</span>
              <span className="val">{row.forum || row.forumId || '—'}</span>
            </div>
            <div className="detail-field">
              <span className="lbl">来源板块 / 分类</span>
              <span className="val">{row.board}</span>
            </div>
            <div className="detail-field">
              <span className="lbl">来源类型</span>
              <span className="val">
                {row.sourceType === 'upload' ? '人工导入 (upload)' : '论坛爬取 (web)'}
              </span>
            </div>
            {row.sourceUrl ? (
              <div className="detail-field full">
                <span className="hint">点「已入库重爬」会重新抓取该帖并按 hash 覆盖更新，不会新增同标题重复行。</span>
              </div>
            ) : (
              <div className="detail-field full">
                <span className="hint">无帖子来源链接，无法重爬。</span>
              </div>
            )}
          </div>
        ) : (
          <div className="detail-grid">
            <div className="detail-field full">
              <span className="lbl">描述</span>
              <pre className="val desc-block">
                {formatBoardDescription(row.description, row.boardFid) || '无描述'}
              </pre>
            </div>
            <div className="detail-field full">
              <span className="lbl">预览图</span>
              {row.previewImages?.length ? (
                <DetailPreviewGrid urls={row.previewImages} />
              ) : (
                <span className="val hint">无预览图</span>
              )}
            </div>
            {row.password ? (
              <div className="detail-field">
                <span className="lbl">解压密码</span>
                <span className="val">
                  <code>{row.password}</code>
                </span>
              </div>
            ) : null}
            <div className="detail-field full">
              <span className="lbl">链接</span>
              {row.links?.length ? (
                <ul className="link-list">
                  {row.links.map((l) => (
                    <li key={l} className="mono">
                      {l}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="val hint">无链接（stub）</span>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
