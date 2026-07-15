export type HealthDb = {
  ok: boolean
  host: string
  port: number
  name: string
  backend: string
  error?: string | null
}

export type HealthResponse = {
  status: string
  db: HealthDb
  schema?: string
}

export function fetchHealth() {
  return fetch('/health', { credentials: 'include' }).then(async (res) => {
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return (await res.json()) as HealthResponse
  })
}
