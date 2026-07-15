import { api } from './client'

export type ForumBoard = {
  fid: string
  name: string
  primary_link: string
  enabled?: boolean
  category?: string
  hot?: boolean
  priority?: number
}

export type ForumCrawlerConfig = {
  web_crawler_enabled: boolean
  web_crawl_urls: string
  web_crawler_interval_minutes: number
  web_crawler_timeout: number
  web_crawler_ua: string
  web_crawler_cookie: string
  web_crawler_auto_discover: boolean
  web_crawler_max_boards_per_run: number
  web_crawler_list_pages_per_board: number
  web_crawler_board_refresh_hours: number
  web_crawler_max_threads_per_run: number
  web_crawler_request_delay: number
  web_crawler_fetch_failure_threshold: number
  web_crawler_fetch_cooldown_seconds: number
  web_crawler_fetch_max_cooldowns: number
  web_crawler_autothrottle_max_delay: number
  web_crawler_autothrottle_window: number
  web_crawler_target_imports: number
  web_crawler_require_structured_desc: boolean
  web_crawler_one_link_per_thread: boolean
  web_crawler_max_list_pages: number
  web_crawler_fetch_retries: number
  web_crawler_thread_timeout: number
  board_order: string[]
  /** 当前爬虫工作板块（一次仅一个） */
  active_board_fid: string
}

/** 板块结构化【标签】/解析差异说明（对齐 ed2k format_guides） */
export type ForumFormatGuide = {
  id: string
  title: string
  primary_link: string
  fids?: string[]
  summary: string
  fields: string[]
  notes: string[]
}

export type ForumItem = {
  id: string
  name: string
  base_url: string
  status: 'active' | 'planned' | string
  /** 本站唯一专用爬虫（色花堂）；其它论坛不可复用其配置 */
  site_dedicated?: boolean
  crawler_registered?: boolean
  crawler_module?: string | null
  board_count?: number
  boards: ForumBoard[]
  /** planned / 未接入论坛为 null，避免套用色花堂通用配置 */
  crawler_config: ForumCrawlerConfig | null
  policies?: string[]
  /** 常用正文【标签】名 */
  structure_labels?: string[]
  /** 分板块解析差异 */
  format_guides?: ForumFormatGuide[]
}

export type ForumRulesResponse = {
  active_forum_id: string
  site_crawler_forum_id?: string
  registered_crawler_forums?: string[]
  forums: ForumItem[]
  forum_configs: Record<string, ForumCrawlerConfig>
}

export function fetchForumRules() {
  return api<ForumRulesResponse>('/api/forum/rules')
}

export function saveForumConfig(forumId: string, config: ForumCrawlerConfig) {
  return api<{ message: string; forum_id: string; config: ForumCrawlerConfig }>(`/api/forum/${forumId}/config`, {
    method: 'PUT',
    body: JSON.stringify({ config }),
  })
}

export function setActiveForum(forumId: string) {
  return api<{ message: string; active_forum_id: string }>('/api/forum/active', {
    method: 'PUT',
    body: JSON.stringify({ active_forum_id: forumId }),
  })
}

export type ForumLinkTestResult = {
  forum_id: string
  ok: boolean
  message: string
  status_code: number | null
  elapsed_ms: number | null
  test_url: string
  proxy?: string
  proxy_used?: boolean
  final_url?: string | null
}

export function testForumLink(forumId: string) {
  return api<ForumLinkTestResult>(`/api/forum/${forumId}/link-test`, {
    method: 'POST',
    body: '{}',
  })
}

export function setActiveBoard(forumId: string, fid: string) {
  return api<{ message: string; forum_id: string; active_board_fid: string; config: ForumCrawlerConfig }>(
    `/api/forum/${forumId}/active-board`,
    {
      method: 'PUT',
      body: JSON.stringify({ fid }),
    },
  )
}

export type ParseThreadBody = {
  url: string
  fid?: string
  proxy?: string
}

export type ParseThreadResult = {
  message?: string
  forum_id?: string
  title?: string
  import_verdict?: string
  final_ed2k_count?: number
  final_magnet_count?: number
  [key: string]: unknown
}

export function parseForumThread(forumId: string, body: ParseThreadBody) {
  return api<ParseThreadResult>(`/api/forum/${forumId}/parse-thread`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
