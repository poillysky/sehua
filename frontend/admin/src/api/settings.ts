import { api } from './client'

export type SiteSettings = {
  web_crawler_proxy: string
  search_frontend_url: string
  web_crawler_interval_minutes: number
  crawl_interval_label: string
}

export function fetchSettings() {
  return api<SiteSettings>('/api/settings')
}

export function saveSettings(body: { web_crawler_proxy: string; search_frontend_url: string }) {
  return api<SiteSettings & { message: string }>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}
