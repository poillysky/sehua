import { api, getToken, localizeErrorMessage } from './client'

export type BackupFileInfo = {
  exists: boolean
  path?: string
  filename?: string
  bytes: number
  mtime?: string | null
}

export type BackupImportJob = {
  active: boolean
  phase: string
  percent: number
  message: string
  filename?: string
  processed?: number
  total?: number
  ok?: boolean | null
  error?: string | null
  stats?: {
    resources_inserted?: number
    resources_updated?: number
    resources_skipped?: number
    tags_upserted?: number
    resource_tags_linked?: number
  } | null
  started_at?: string | null
  finished_at?: string | null
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
  import_job?: BackupImportJob
}

export type ResourceDbConfig = {
  message?: string
  enabled: boolean
  ready?: boolean
  using_primary: boolean
  settings_unavailable?: boolean
  writable?: boolean
  role?: 'multi_terminal' | 'colocated_primary' | 'config_unavailable' | string
  architecture?: {
    metadata_db?: string
    resource_db?: string
  }
  host: string
  port: number | null
  user: string
  dbname: string
  has_password: boolean
  settings_error?: string | null
  env_override?: boolean
  effective?: {
    host: string
    port: number
    user: string
    dbname: string
    has_password: boolean
  }
  primary?: {
    host: string
    port: number
    user: string
    dbname: string
  }
  migrations_applied?: string[]
  connection_ok?: boolean
  connection_error?: string | null
}

export type ResourceDbBody = {
  enabled: boolean
  host?: string
  port?: number | null
  user?: string
  password?: string | null
  dbname?: string
  keep_password?: boolean
}

export function fetchResourceDbConfig() {
  return api<ResourceDbConfig>('/api/system/resource-db')
}

export function saveResourceDbConfig(body: ResourceDbBody) {
  return api<ResourceDbConfig>('/api/system/resource-db', {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function testResourceDbConfig(body: ResourceDbBody) {
  return api<{ message: string; ok: boolean; using_primary?: boolean }>('/api/system/resource-db/test', {
    method: 'POST',
    body: JSON.stringify(body),
  })
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

export type BackupImportStartResult = {
  message: string
  started?: boolean
  ok: boolean
  filename?: string
  bytes?: number
  busy?: boolean
  import_job?: BackupImportJob
  error?: string
}

export type BackupImportStatus = {
  message?: string
  busy: boolean
  import_job: BackupImportJob
}

export function fetchBackupImportStatus() {
  return api<BackupImportStatus>('/api/system/backup/import/status')
}

export async function importBackupFile(
  file: File,
  opts?: { onProgress?: (pct: number) => void },
): Promise<BackupImportStartResult> {
  const form = new FormData()
  form.append('file', file)

  const token = getToken()

  // XHR：可显示上传进度；大文件在「请求到达后端写活动日志」之前会卡很久
  const res = await new Promise<Response>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/system/backup/import')
    xhr.withCredentials = true
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = (ev) => {
      if (!ev.lengthComputable || !opts?.onProgress) return
      // 上传阶段占整体 0–15%，解析合并由后端进度接口覆盖
      opts.onProgress(Math.min(15, Math.round((ev.loaded / ev.total) * 15)))
    }
    xhr.onload = () => {
      opts?.onProgress?.(15)
      resolve(
        new Response(xhr.responseText, {
          status: xhr.status,
          statusText: xhr.statusText,
          headers: { 'Content-Type': xhr.getResponseHeader('Content-Type') || 'application/json' },
        }),
      )
    }
    xhr.onerror = () => reject(new Error('网络错误：备份上传中断'))
    xhr.ontimeout = () => reject(new Error('上传超时：文件过大或反代超时过短'))
    // 0 = 不限；实际仍受 Nginx / 外层反代限制
    xhr.timeout = 0
    xhr.send(form)
  })

  if (res.status === 401) {
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) {
    if (res.status === 413) {
      throw new Error('上传文件太大，被服务器拒绝。请缩小文件或联系管理员调大上传限制')
    }
    let detail: unknown = null
    try {
      const data = await res.json()
      detail = data.detail ?? data.message
    } catch {
      /* ignore */
    }
    throw new Error(
      localizeErrorMessage(
        detail,
        res.status === 409 ? '正在备份或导入，请稍候再试' : '导入失败，请稍后重试',
      ),
    )
  }
  return (await res.json()) as BackupImportStartResult
}
