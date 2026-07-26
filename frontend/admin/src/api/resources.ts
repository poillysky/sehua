import { api } from './client'

export type ApiResourceAsset = {
  hash: string
  filename?: string | null
  size?: number
  ed2k_link?: string | null
  preview_images?: string[]
  link_kind?: string
}

export type ApiResource = {
  id?: number
  hash: string
  hashes?: string[]
  filename: string
  size: number
  ed2k_link: string
  updated_at: string | null
  title: string | null
  description: string | null
  source_url: string | null
  board_fid: string | null
  board_name: string | null
  forum_id?: string | null
  forum_name?: string | null
  ed2k_links: string[]
  extract_password: string | null
  source_key: string
  source_type: string
  preview_images?: string[]
  import_outcome?: string | null
  link_kind: 'magnet' | 'ed2k' | '115share' | 'stub' | 'failed' | string
  asset_count?: number
  assets?: ApiResourceAsset[]
}

export type ResourceAsset = {
  hash: string
  filename?: string
  size?: number
  link?: string
  previewImages?: string[]
  result?: ResourceRow['result']
}

export type ResourceRow = {
  id: string
  title: string
  forum?: string
  forumId?: string
  board: string
  boardFid?: string
  outcome: string
  result: 'magnet' | 'ed2k' | '115share' | 'stub' | 'failed'
  time: string
  sourceUrl?: string
  sourceType?: string
  description?: string
  password?: string
  links?: string[]
  filename?: string
  hash?: string
  /** 同帖全部子资源 hash；删除时应全部提交 */
  hashes?: string[]
  assetCount?: number
  assets?: ResourceAsset[]
  previewImages?: string[]
}

export type ResourceFacets = {
  sources: Record<string, number>
  boards: Array<{ name: string; count: number }>
  forums?: Array<{ id: string; name: string; count: number }>
  results?: Record<string, number>
}

export type ResourcesPageResult = {
  items: ApiResource[]
  count: number
  total: number
  page: number
  page_size: number
  pages: number
  boards: string[]
  facets?: ResourceFacets
}

const KIND_OUTCOME: Record<string, string> = {
  magnet: '已提取主链',
  ed2k: '已提取主链',
  '115share': '已提取115分享',
  stub: '无下载链 · 占位入库',
  failed: '解析失败',
}

function formatOutcome(kind: string, importOutcome?: string | null): string {
  const detail = (importOutcome || '').trim()
  if (detail) {
    if (kind === 'stub') return detail.includes('占位') ? detail : `${detail} · 占位入库`
    return detail
  }
  return KIND_OUTCOME[kind] || kind
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 展示主板块 · 子分类；兼容旧库「国产原创-国产无码」；无名称时尽量不显示裸 fid */
export function formatSourceBoard(boardName?: string | null, boardFid?: string | null): string {
  const raw = (boardName || '').trim()
  if (raw) {
    if (raw.includes(' · ')) return raw
    const i = raw.indexOf('-')
    if (i > 0 && i < raw.length - 1) return `${raw.slice(0, i)} · ${raw.slice(i + 1)}`
    if (/^fid[-\s]?\d+/i.test(raw)) {
      // 旧脏数据「fid-2」当作无名称
    } else {
      return raw
    }
  }
  const fid = (boardFid || '').trim()
  if (!fid) return '—'
  // 有子版 key 时至少展示 key，避免「fid 2」这种空名
  if (fid.includes(':')) return fid
  return `fid ${fid}`
}

/** 从板块展示名拆出主板块 / 子分类 */
export function splitBoardParentChild(name: string): { parent: string; child: string | null } {
  const raw = (name || '').trim()
  if (!raw) return { parent: '', child: null }
  const mid = raw.indexOf(' · ')
  if (mid > 0) {
    return { parent: raw.slice(0, mid).trim(), child: raw.slice(mid + 3).trim() || null }
  }
  const dash = raw.indexOf('-')
  if (dash > 0 && dash < raw.length - 1) {
    return { parent: raw.slice(0, dash).trim(), child: raw.slice(dash + 1).trim() || null }
  }
  return { parent: raw, child: null }
}

export type BoardFacetItem = { name: string; count: number }

export type BoardFacetTreeNode = {
  parent: string
  total: number
  /** 恰好等于主板块名的旧数据行 */
  self: BoardFacetItem | null
  children: { name: string; label: string; count: number }[]
  /** 点击主节点是否可筛（色花堂主板块=可；2048 分区名不可直接筛） */
  parentFilterable?: boolean
}

/** 资源侧栏：按主板块分组，子分类挂在下面（仅靠名称拆分，作兜底） */
export function buildBoardFacetTree(items: BoardFacetItem[]): BoardFacetTreeNode[] {
  const map = new Map<string, BoardFacetTreeNode>()

  const ensure = (parent: string) => {
    let node = map.get(parent)
    if (!node) {
      node = { parent, total: 0, self: null, children: [], parentFilterable: true }
      map.set(parent, node)
    }
    return node
  }

  for (const item of items) {
    const name = (item.name || '').trim()
    if (!name) continue
    const count = Number(item.count) || 0
    const { parent, child } = splitBoardParentChild(name)
    if (!parent) continue
    const node = ensure(parent)
    if (child) {
      node.children.push({ name, label: child, count })
      node.total += count
    } else {
      node.self = { name, count }
      node.total += count
    }
  }

  for (const node of map.values()) {
    node.children.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'zh'))
  }

  return [...map.values()].sort((a, b) => b.total - a.total || a.parent.localeCompare(b.parent, 'zh'))
}

type TopologyBoard = {
  name: string
  board_name?: string
  type_name?: string
  category?: string
  priority?: number
}

/**
 * 按论坛拓扑建树（比纯名称拆分准确）：
 * - 色花堂：主板块 board_name → 子类 type_name
 * - 2048：分区 category → 子版 board_name
 */
export function buildForumBoardFacetTree(
  forumId: string,
  topology: TopologyBoard[],
  facets: BoardFacetItem[],
): BoardFacetTreeNode[] {
  const countOf = (name: string) => {
    const hit = facets.find((f) => f.name === name)
    return hit ? Number(hit.count) || 0 : 0
  }
  const used = new Set<string>()
  const nodes: BoardFacetTreeNode[] = []

  if ((forumId || '').trim() === '2048') {
    const byCat = new Map<string, TopologyBoard[]>()
    for (const b of topology) {
      const cat = (b.category || '其它').trim() || '其它'
      const list = byCat.get(cat) || []
      list.push(b)
      byCat.set(cat, list)
    }
    for (const [cat, list] of byCat) {
      const children: BoardFacetTreeNode['children'] = []
      let total = 0
      const seen = new Set<string>()
      for (const b of [...list].sort(
        (a, b) => (a.priority ?? 50) - (b.priority ?? 50) || (a.board_name || a.name).localeCompare(b.board_name || b.name, 'zh'),
      )) {
        const leaf = (b.board_name || b.name || '').trim()
        if (!leaf || seen.has(leaf)) continue
        seen.add(leaf)
        const count = countOf(leaf)
        used.add(leaf)
        children.push({ name: leaf, label: leaf, count })
        total += count
      }
      if (!children.length) continue
      nodes.push({
        parent: cat,
        total,
        self: null,
        children,
        parentFilterable: false,
      })
    }
  } else {
    // 色花堂等：board_name → 子类
    const byParent = new Map<string, TopologyBoard[]>()
    for (const b of topology) {
      const parent =
        (b.board_name || '').trim() ||
        splitBoardParentChild(b.name || '').parent ||
        (b.name || '').trim()
      if (!parent) continue
      const list = byParent.get(parent) || []
      list.push(b)
      byParent.set(parent, list)
    }
    for (const [parent, list] of byParent) {
      const children: BoardFacetTreeNode['children'] = []
      let self: BoardFacetItem | null = null
      let total = 0
      const seenChild = new Set<string>()
      for (const b of [...list].sort(
        (a, b) => (a.priority ?? 50) - (b.priority ?? 50) || (a.type_name || a.name).localeCompare(b.type_name || b.name, 'zh'),
      )) {
        const full = (b.name || '').trim()
        const typeName = (b.type_name || '').trim()
        if (!full) continue
        if (!typeName) {
          // 整板
          const count = countOf(full)
          used.add(full)
          if (full === parent) {
            self = { name: full, count }
            total += count
          } else if (!seenChild.has(full)) {
            seenChild.add(full)
            children.push({ name: full, label: full, count })
            total += count
          }
          continue
        }
        if (seenChild.has(full)) continue
        seenChild.add(full)
        const count = countOf(full)
        used.add(full)
        children.push({ name: full, label: typeName, count })
        total += count
      }
      // 库内「主板块」整板计数（无 · 后缀）若拓扑未单独列出
      if (!self) {
        const alone = countOf(parent)
        if (alone > 0) {
          self = { name: parent, count: alone }
          total += alone
          used.add(parent)
        }
      }
      if (!self && !children.length) continue
      nodes.push({
        parent,
        total,
        self,
        children,
        parentFilterable: true,
      })
    }
  }

  // 拓扑外仍有计数的板块（脏名/历史名）归入「其它」
  const orphans = facets.filter((f) => {
    const n = (f.name || '').trim()
    return n && n !== '未分类' && !used.has(n) && (Number(f.count) || 0) > 0
  })
  if (orphans.length) {
    const children = orphans
      .map((f) => {
        const { child } = splitBoardParentChild(f.name)
        return {
          name: f.name,
          label: child || f.name,
          count: Number(f.count) || 0,
        }
      })
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'zh'))
    nodes.push({
      parent: '其它',
      total: children.reduce((s, c) => s + c.count, 0),
      self: null,
      children,
      parentFilterable: false,
    })
  }

  return nodes.sort((a, b) => b.total - a.total || a.parent.localeCompare(b.parent, 'zh'))
}

export function mapApiResource(item: ApiResource): ResourceRow {
  const kind = (['magnet', 'ed2k', '115share', 'stub', 'failed'].includes(item.link_kind)
    ? item.link_kind
    : 'failed') as ResourceRow['result']
  const links = item.ed2k_links?.length ? item.ed2k_links : item.ed2k_link ? [item.ed2k_link] : []
  const hashes =
    item.hashes?.length
      ? item.hashes
      : item.hash
        ? [item.hash]
        : []
  const assets: ResourceAsset[] = (item.assets || []).map((a) => {
    const ak = (['magnet', 'ed2k', '115share', 'stub', 'failed'].includes(String(a.link_kind))
      ? a.link_kind
      : kind) as ResourceRow['result']
    return {
      hash: a.hash,
      filename: a.filename || undefined,
      size: a.size,
      link: a.ed2k_link || undefined,
      previewImages: a.preview_images?.length ? a.preview_images : undefined,
      result: ak,
    }
  })
  return {
    id: item.id != null ? String(item.id) : item.hash,
    title: item.title || item.filename || item.hash,
    forum: item.forum_name || item.forum_id || undefined,
    forumId: item.forum_id || undefined,
    board: formatSourceBoard(item.board_name, item.board_fid),
    boardFid: item.board_fid || undefined,
    outcome: formatOutcome(kind, item.import_outcome),
    result: kind,
    time: formatTime(item.updated_at),
    sourceUrl: item.source_url || undefined,
    sourceType: item.source_type,
    description: item.description || undefined,
    password: item.extract_password || undefined,
    links,
    filename: item.filename,
    hash: item.hash,
    hashes,
    assetCount: item.asset_count ?? hashes.length,
    assets: assets.length ? assets : undefined,
    previewImages: item.preview_images?.length ? item.preview_images : undefined,
  }
}

export const PAGE_SIZE = 30

export function fetchRecentResources(params: {
  page?: number
  pageSize?: number
  source?: string
  board?: string
  result?: string
  forum?: string
  q?: string
}) {
  const page = params.page ?? 1
  const pageSize = params.pageSize ?? PAGE_SIZE
  const sp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (params.source && params.source !== 'all') sp.set('source', params.source)
  if (params.board && params.board !== 'all') sp.set('board', params.board)
  if (params.result && params.result !== 'all') sp.set('result', params.result)
  if (params.forum && params.forum !== 'all') sp.set('forum', params.forum)
  if (params.q?.trim()) sp.set('q', params.q.trim())
  return api<ResourcesPageResult>(`/api/resources/recent?${sp}`)
}

export type ResourceSelectionItem = {
  id: number
  hash: string
  hashes?: string[]
  source_url?: string | null
  title?: string | null
  link_kind?: string
  asset_count?: number
}

export type ResourceIdsResult = {
  items: ResourceSelectionItem[]
  count: number
  total: number
  limit: number
  truncated: boolean
  ids: number[]
  hashes: string[]
}

/** 当前筛选下全部资源 id（跨页全选） */
export function fetchResourceIds(params: {
  source?: string
  board?: string
  result?: string
  forum?: string
  q?: string
  limit?: number
}) {
  const sp = new URLSearchParams()
  if (params.source && params.source !== 'all') sp.set('source', params.source)
  if (params.board && params.board !== 'all') sp.set('board', params.board)
  if (params.result && params.result !== 'all') sp.set('result', params.result)
  if (params.forum && params.forum !== 'all') sp.set('forum', params.forum)
  if (params.q?.trim()) sp.set('q', params.q.trim())
  if (params.limit) sp.set('limit', String(params.limit))
  const qs = sp.toString()
  return api<ResourceIdsResult>(`/api/resources/ids${qs ? `?${qs}` : ''}`)
}

export function fetchDataOverview() {
  return api<{
    message?: string
    overview: {
      resources: number
      resource_sources: number
      import_jobs: number
      crawl_pages: number
      crawl_pending: number
      crawl_boards: number
      activity_logs: number
      sources?: number
      boards?: number
    }
    crawler_running: boolean
    crawler_enabled: boolean
  }>('/api/system/data-overview')
}

export type RecrawlItemResult = {
  ok: boolean
  imported?: boolean
  removed?: boolean
  queued?: boolean
  hash?: string
  tid?: number
  url?: string
  title?: string
  verdict?: string
  verdict_label?: string
  outcome?: string
  note?: string
  error?: string
}

export function deleteResource(hash: string) {
  return api<{ message: string; hash: string; deleted: boolean }>('/api/resources/delete', {
    method: 'POST',
    body: JSON.stringify({ hash }),
  })
}

export function deleteResourcesBatch(hashes: string[]) {
  return api<{
    message: string
    deleted: number
    missing: number
    requested: number
  }>('/api/resources/delete-batch', {
    method: 'POST',
    body: JSON.stringify({ hashes }),
  })
}

export function recrawlResource(hash: string) {
  return api<{
    message: string
    result: RecrawlItemResult
  }>('/api/resources/recrawl', {
    method: 'POST',
    body: JSON.stringify({ hash }),
  })
}

export function recrawlResourcesBatch(hashes: string[]) {
  return api<{
    message: string
    result: {
      ok: boolean
      mode?: 'immediate' | 'queued' | 'background' | 'failed'
      started?: number
      imported?: number
      removed?: number
      queued?: number
      failed?: number
      note?: string
      error?: string
      items?: RecrawlItemResult[]
    }
  }>('/api/resources/recrawl-batch', {
    method: 'POST',
    body: JSON.stringify({ hashes }),
  })
}
