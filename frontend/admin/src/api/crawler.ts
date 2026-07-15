import { api } from './client'

export type CrawlerActivity = { t: string; msg: string }

export type CrawlerStatus = {
  forum_id: string
  active_forum_id: string
  active_forum_name?: string
  enabled: boolean
  active_board_fid: string
  request_delay?: number
  list_pages_per_board?: number
  interval_minutes: number
  interval_label: string
  running: boolean
  looping?: boolean
  stopping?: boolean
  phase: string
  list_sort?: string
  list_sort_label?: string
  last_started_at?: string | null
  last_finished_at?: string | null
  last_result?: Record<string, unknown> | null
  activity: CrawlerActivity[]
  boards: { fid: string; name: string; pending: string | number; done: string | number }[]
  queue?: {
    ready?: number
    soft_ad?: number
    abnormal?: number
    deferred?: number
    total_pending?: number
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
