import { useEffect, useSyncExternalStore, type ReactNode } from 'react'

export type ToastKind = 'success' | 'error' | 'info' | 'warn'

export type ToastItem = {
  id: string
  kind: ToastKind
  message: string
  title?: string
  duration: number
}

type ToastOptions = {
  title?: string
  duration?: number
}

type Listener = () => void

const DEFAULT_DURATION: Record<ToastKind, number> = {
  success: 3200,
  info: 3600,
  warn: 4200,
  error: 5200,
}

const TITLE: Record<ToastKind, string> = {
  success: '成功',
  info: '提示',
  warn: '注意',
  error: '错误',
}

let seq = 0
let toasts: ToastItem[] = []
const listeners = new Set<Listener>()

function emit() {
  for (const listener of listeners) listener()
}

function push(kind: ToastKind, message: string, options?: ToastOptions) {
  const text = String(message || '').trim()
  if (!text) return ''
  const id = `t-${Date.now()}-${++seq}`
  const item: ToastItem = {
    id,
    kind,
    message: text,
    title: options?.title || TITLE[kind],
    duration: options?.duration ?? DEFAULT_DURATION[kind],
  }
  toasts = [item, ...toasts].slice(0, 5)
  emit()
  return id
}

function dismiss(id: string) {
  const next = toasts.filter((t) => t.id !== id)
  if (next.length === toasts.length) return
  toasts = next
  emit()
}

function subscribe(listener: Listener) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot() {
  return toasts
}

export const toast = {
  show(message: string, options?: ToastOptions & { kind?: ToastKind }) {
    return push(options?.kind || 'info', message, options)
  },
  success(message: string, options?: ToastOptions) {
    return push('success', message, options)
  },
  info(message: string, options?: ToastOptions) {
    return push('info', message, options)
  },
  warn(message: string, options?: ToastOptions) {
    return push('warn', message, options)
  },
  error(message: string, options?: ToastOptions) {
    return push('error', message, options)
  },
  dismiss,
}

function ToastIcon({ kind }: { kind: ToastKind }) {
  if (kind === 'success') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M8.5 12.5l2.5 2.5 4.5-5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (kind === 'error') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
        <circle cx="12" cy="12" r="9" />
        <path d="M9 9l6 6M15 9l-6 6" strokeLinecap="round" />
      </svg>
    )
  }
  if (kind === 'warn') {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
        <path d="M12 3.8L21 20H3L12 3.8z" strokeLinejoin="round" />
        <path d="M12 10v4.5M12 17.5h.01" strokeLinecap="round" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5M12 16.5h.01" strokeLinecap="round" />
    </svg>
  )
}

function ToastCard({ item }: { item: ToastItem }) {
  useEffect(() => {
    if (item.duration <= 0) return
    const timer = window.setTimeout(() => toast.dismiss(item.id), item.duration)
    return () => window.clearTimeout(timer)
  }, [item.id, item.duration])

  return (
    <div className={`app-toast app-toast--${item.kind}`} role="status" aria-live="polite">
      <span className="app-toast-icon" aria-hidden>
        <ToastIcon kind={item.kind} />
      </span>
      <div className="app-toast-body">
        {item.title ? <strong className="app-toast-title">{item.title}</strong> : null}
        <p className="app-toast-msg">{item.message}</p>
      </div>
      <button type="button" className="app-toast-close" aria-label="关闭" onClick={() => toast.dismiss(item.id)}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
        </svg>
      </button>
      {item.duration > 0 ? (
        <span
          className="app-toast-progress"
          style={{ animationDuration: `${item.duration}ms` }}
          aria-hidden
        />
      ) : null}
    </div>
  )
}

export function ToastHost() {
  const items = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  if (!items.length) return null
  return (
    <div className="app-toast-host" aria-label="消息提示">
      {items.map((item) => (
        <ToastCard key={item.id} item={item} />
      ))}
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <ToastHost />
    </>
  )
}
