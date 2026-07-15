import { api, getToken } from './client'

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

export function fetchImportSpec() {
  return api<ImportSpec>('/api/import/spec')
}

export function importText(body: ImportPayload) {
  return api<ImportResult>('/api/import/', {
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
    let detail: unknown = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
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
    let detail: unknown = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return (await res.json()) as ImportResult
}
