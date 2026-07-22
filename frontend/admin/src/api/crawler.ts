import { api } from './client'

export type CrawlerActivity = { t: string; msg: string }

export type CrawlerStatus = {
  forum_id: string
  active_forum_id: string
  active_forum_name?: string
  enabled: boolean
  active_board_fid: string
  enabled_board_fids?: string[]
  request_delay?: number
  list_pages_per_board?: number
  interval_minutes: number
  interval_label: string
  running: boolean
  looping?: boolean
  loop_kind?: string | null
  stopping?: boolean
  phase: string
  list_sort?: string
  list_sort_label?: string
  last_started_at?: string | null
  last_finished_at?: string | null
  last_result?: Record<string, unknown> | null
  random_progress?: {
    active?: boolean
    probe_budget?: number
    probed?: number
    imported?: number
    stubbed?: number
    missing?: number
    skipped_dup?: number
    failed?: number
    skipped?: number
    session_probed?: number
  }
  account_stub_progress?: {
    active?: boolean
    remaining?: number
    budget?: number
    done?: number
    upgraded?: number
    still_stub?: number
    failed?: number
    skipped_prep?: number
    current_tid?: number | null
    current_title?: string
  }
  board_list_cursors?: Record<string, number>
  activity: CrawlerActivity[]
  boards: { fid: string; name: string; pending: string | number; done: string | number }[]
  queue?: {
    ready?: number
    soft_ad?: number
    abnormal?: number
    deferred?: number
    total_pending?: number
  }
  discarded?: {
    failed?: number
    skipped?: number
    total?: number
  }
  throttle?: { fetch_delay_current?: number; fetch_success_rate?: number | null }
  metrics: {
    discovered: number
    enqueued?: number
    crawled: number
    imports: number
    stubs: number
    retries: number
    soft_browser_retried: number
    queue_ready?: number
    queue_soft_ad?: number
    queue_abnormal?: number
    queue_deferred?: number
    discarded_failed?: number
    discarded_skipped?: number
    discarded_total?: number
    random_probed?: number
    random_budget?: number
    random_imported?: number
    random_session?: number
    stub_done?: number
    stub_budget?: number
    stub_remaining?: number
    stub_upgraded?: number
    priority_stubs?: number
    discarded_access_denied_title?: number
    discarded_failed_kind?: number
    account_pass_total?: number
    board_updated?: number
  }
}

export function fetchCrawlerStatus() {
  return api<CrawlerStatus>('/api/crawler/status')
}

export function setCrawlerEnabled(enabled: boolean) {
  return api<{ message: string; enabled: boolean }>('/api/crawler/enabled', {
    method: 'PUT',
    body: JSON.stringify({ enabled }),
  })
}

export function runCrawlerOnce(opts?: { max_threads?: number; persist?: boolean; scan_list?: boolean }) {
  return api<{ message: string; result: Record<string, unknown> }>('/api/crawler/run', {
    method: 'POST',
    body: JSON.stringify(opts || {}),
  })
}

export function scanHeadOnce(opts?: { max_pages?: number; persist?: boolean }) {
  return api<{ message: string; result: Record<string, unknown> }>('/api/crawler/scan-head', {
    method: 'POST',
    body: JSON.stringify(opts || {}),
  })
}

export function randomTidOnce(opts?: {
  count?: number
  import_target?: number
  tid_min?: number
  tid_max?: number
  persist?: boolean
}) {
  return api<{
    message: string
    result: Record<string, unknown>
    probed: number
    imported: number
    stubbed: number
    missing: number
    skipped_dup: number
  }>('/api/crawler/random-tid', {
    method: 'POST',
    body: JSON.stringify(opts || {}),
  })
}

export function startRandomTidLoop(opts?: {
  count?: number
  tid_min?: number
  tid_max?: number
}) {
  return api<{
    message: string
    looping: boolean
    loop_kind?: string
    probe?: number
    already?: boolean
  }>('/api/crawler/random-tid/loop/start', {
    method: 'POST',
    body: JSON.stringify(opts || { count: 200 }),
  })
}

export function startCrawlerLoop() {
  return api<{ message: string; looping: boolean }>('/api/crawler/loop/start', {
    method: 'POST',
    body: '{}',
  })
}

export function stopCrawlerLoop() {
  return api<{ message: string; looping: boolean }>('/api/crawler/loop/stop', {
    method: 'POST',
    body: '{}',
  })
}

export function stopCrawler() {
  return api<{
    message: string
    ok?: boolean
    was_running?: boolean
    forced?: boolean
    queue_preserved?: boolean
    running?: boolean
    looping?: boolean
  }>('/api/crawler/stop', {
    method: 'POST',
    body: '{}',
  })
}

export type QueueRetryResult = {
  message: string
  kind: 'abnormal' | 'soft_ad' | string
  crawled?: number
  imports?: number
  stubs?: number
  retries?: number
  failed?: number
  result?: Record<string, unknown>
}

export function retryAbnormalQueue() {
  return api<QueueRetryResult>('/api/crawler/queue/retry-abnormal', {
    method: 'POST',
    body: '{}',
  })
}

export function retrySoftAdQueue() {
  return api<QueueRetryResult>('/api/crawler/queue/retry-soft-ad', {
    method: 'POST',
    body: '{}',
  })
}

export type DiscardedQueueItem = {
  url: string
  tid?: number | null
  thread_title?: string | null
  board_fid?: string | null
  board_name?: string | null
  forum_id?: string | null
  status: 'failed' | 'skipped' | string
  outcome?: string | null
  last_error?: string | null
  fetch_fail_count?: number | null
  crawled_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type DiscardedQueueResult = {
  status: 'all' | 'failed' | 'skipped' | string
  q: string
  limit: number
  offset: number
  total: number
  counts: { failed: number; skipped: number; total: number }
  kind_counts?: Record<string, number>
  items: DiscardedQueueItem[]
}

export function fetchDiscardedQueue(params?: {
  status?: 'all' | 'failed' | 'skipped'
  q?: string
  limit?: number
  offset?: number
}) {
  const sp = new URLSearchParams()
  if (params?.status) sp.set('status', params.status)
  if (params?.q) sp.set('q', params.q)
  if (params?.limit != null) sp.set('limit', String(params.limit))
  if (params?.offset != null) sp.set('offset', String(params.offset))
  const qs = sp.toString()
  return api<DiscardedQueueResult>(`/api/crawler/queue/discarded${qs ? `?${qs}` : ''}`)
}

export type QueueBrowseKind = 'ready' | 'abnormal' | 'discarded' | 'stubs'

export type QueueBrowseItem = DiscardedQueueItem & {
  hash?: string | null
  source_url?: string | null
  title?: string | null
  import_outcome?: string | null
  ed2k_link?: string | null
  retry_after?: string | null
}

export type QueueBrowseResult = {
  kind: QueueBrowseKind | string
  status?: string
  q: string
  reason?: string
  limit: number
  offset: number
  total: number
  counts?: { failed: number; skipped: number; total: number }
  kind_counts?: Record<string, number>
  reasons?: Array<{ reason: string; count: number }>
  items: QueueBrowseItem[]
}

export function fetchQueueBrowse(params: {
  kind: QueueBrowseKind
  status?: 'all' | 'failed' | 'skipped'
  q?: string
  reason?: string
  limit?: number
  offset?: number
}) {
  const sp = new URLSearchParams()
  sp.set('kind', params.kind)
  if (params.status) sp.set('status', params.status)
  if (params.q) sp.set('q', params.q)
  if (params.reason) sp.set('reason', params.reason)
  if (params.limit != null) sp.set('limit', String(params.limit))
  if (params.offset != null) sp.set('offset', String(params.offset))
  return api<QueueBrowseResult>(`/api/crawler/queue/browse?${sp.toString()}`)
}

export type DiscardedRequeueResult = {
  message: string
  kind: string
  label: string
  matched: number
  requeued: number
  kind_remaining?: number
  pending_ready?: number
  note?: string
  crawl?: {
    crawled?: number
    imports?: number
    stubs?: number
    skipped?: number
    retries?: number
    failed?: number
  } | null
}

export function requeueDiscardedKind(body?: {
  kind?: string
  start_crawl?: boolean
}) {
  return api<DiscardedRequeueResult>('/api/crawler/queue/discarded/requeue', {
    method: 'POST',
    body: JSON.stringify({
      kind: body?.kind || 'access_denied_bad_title',
      start_crawl: body?.start_crawl !== false,
    }),
  })
}

export type RecrawlStubsResult = {
  message: string
  started?: boolean
  remaining?: number
  budget?: number
  stub_remaining?: number
  discarded_remaining?: number
  note?: string
  processed: number
  upgraded: number
  still_stub: number
  failed: number
  result?: Record<string, unknown>
}

export function recrawlAccountStubs() {
  return api<RecrawlStubsResult>('/api/crawler/recrawl-stubs', {
    method: 'POST',
    body: '{}',
  })
}
