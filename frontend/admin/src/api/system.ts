import { api, getToken, setToken } from './client'

export type BackupFileInfo = {
  exists: boolean
  path?: string
  filename?: string
  bytes: number
  mtime?: string | null
}

export type BackupStatus = {
  message?: string
  enabled: boolean
  hour: number
  minute: number
  last_ok?: boolean
  last_at?: string | null
  last_error?: string | null
  last_bytes?: number
  last_run_date?: string | null
  file: BackupFileInfo
  busy?: boolean
}

export function fetchBackupStatus() {
  return api<BackupStatus>('/api/system/backup')
}

export function saveBackupConfig(body: { enabled?: boolean; hour?: number; minute?: number }) {
  return api<BackupStatus>('/api/system/backup', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function runBackupNow() {
  return api<{
    message: string
    ok: boolean
    bytes?: number
    error?: string
    file?: BackupFileInfo
    result?: Record<string, unknown>
  }>('/api/system/backup/run', {
    method: 'POST',
    body: '{}',
  })
}

export type BackupImportResult = {
  message: string
  ok: boolean
  error?: string
  resources_inserted: number
  resources_updated: number
  resources_skipped: number
  tags_upserted: number
  resource_tags_linked: number
  result?: Record<string, unknown>
}

export async function importBackupFile(file: File): Promise<BackupImportResult> {
  const form = new FormData()
  form.append('file', file)

  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch('/api/system/backup/import', {
    method: 'POST',
    headers,
    body: form,
    credentials: 'include',
  })
  if (res.status === 401) {
    setToken(null)
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) {
    if (res.status === 413) {
      throw new Error('上传文件过大（413）。请更新管理端镜像，或确认 Nginx client_max_body_size 已放宽')
    }
    let detail: unknown = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail ?? data.message ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return (await res.json()) as BackupImportResult
}
