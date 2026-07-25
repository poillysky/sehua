import { api, getToken, localizeErrorMessage } from './client'

export type ImportFormatField = {
  no: number
  name: string
  note?: string
  key?: string
}

export type ImportSpec = {
  title: string
  goal: string
  resource_format: ImportFormatField[]
  ed2k_format: string
  magnet_format?: string
  filename_rules: string[]
  input_methods: string[]
  example: string
  notes?: string[]
}

export type ImportPayload = {
  title?: string
  file_size?: number | null
  preview_images?: string[]
  forum_name?: string
  board_name?: string
  links: string
  source_url?: string
  extract_password?: string
}

export type ImportResult = {
  count: number
  message: string
  ed2k?: number
  magnets?: number
}

export type ImportFromUrlPayload = {
  url: string
  forum_id: string
  board_fid?: string
}

export type ImportFromUrlResult = {
  message: string
  count: number
  forum_id: string
  title?: string
  link_kind?: string
  stub?: boolean
  hash?: string | null
  import_outcome?: string
  board_fid?: string
  board_name?: string
  source_url?: string
  magnets?: number
  ed2k?: number
}

export function fetchImportSpec() {
  return api<ImportSpec>('/api/import/spec')
}

export function importText(body: ImportPayload) {
  return api<ImportResult>('/api/import/', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function importFromUrl(body: ImportFromUrlPayload) {
  return api<ImportFromUrlResult>('/api/import/from-url', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function uploadPreviewImages(files: File[]): Promise<string[]> {
  if (!files.length) return []
  const form = new FormData()
  for (const file of files) form.append('files', file)

  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch('/api/import/preview', {
    method: 'POST',
    headers,
    body: form,
    credentials: 'include',
  })
  if (res.status === 401) throw new Error('未登录或登录已过期')
  if (!res.ok) {
    let detail: unknown = null
    try {
      const data = await res.json()
      detail = data.detail || data.message
    } catch {
      /* ignore */
    }
    throw new Error(
      localizeErrorMessage(
        detail,
        res.status === 409 ? '当前有其他任务在进行，请稍后再试' : '操作失败，请稍后重试',
      ),
    )
  }
  const data = (await res.json()) as { urls?: string[] }
  return data.urls || []
}

export async function importFile(file: File, meta?: Omit<ImportPayload, 'links'>): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  if (meta?.title) form.append('title', meta.title)
  if (meta?.file_size != null && meta.file_size > 0) form.append('file_size', String(meta.file_size))
  if (meta?.preview_images?.length) form.append('preview_images', meta.preview_images.join('\n'))
  if (meta?.forum_name) form.append('forum_name', meta.forum_name)
  if (meta?.board_name) form.append('board_name', meta.board_name)
  if (meta?.source_url) form.append('source_url', meta.source_url)
  if (meta?.extract_password) form.append('extract_password', meta.extract_password)

  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch('/api/import/file', {
    method: 'POST',
    headers,
    body: form,
    credentials: 'include',
  })
  if (res.status === 401) {
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) {
    let detail: unknown = null
    try {
      const data = await res.json()
      detail = data.detail || data.message
    } catch {
      /* ignore */
    }
    throw new Error(
      localizeErrorMessage(
        detail,
        res.status === 409 ? '当前有其他任务在进行，请稍后再试' : '导入失败，请稍后重试',
      ),
    )
  }
  return (await res.json()) as ImportResult
}
