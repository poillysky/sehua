import { api } from './client'

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
