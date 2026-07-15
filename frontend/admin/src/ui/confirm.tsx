import { useEffect, useSyncExternalStore, type ReactNode } from 'react'

export type ConfirmOptions = {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  /** 危险操作：确定按钮用红色 */
  danger?: boolean
}

type ConfirmRequest = ConfirmOptions & {
  id: string
  resolve: (ok: boolean) => void
}

type Listener = () => void

let seq = 0
let current: ConfirmRequest | null = null
const listeners = new Set<Listener>()
const queue: ConfirmRequest[] = []

function emit() {
  for (const listener of listeners) listener()
}

function subscribe(listener: Listener) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot() {
  return current
}

function openNext() {
  if (current || !queue.length) {
    emit()
    return
  }
  current = queue.shift() || null
  emit()
}

function finish(ok: boolean) {
  if (!current) return
  const { resolve } = current
  current = null
  resolve(ok)
  openNext()
}

/** 站内中文确认框，替代浏览器原生 confirm（避免 OK/Cancel 英文按钮）。 */
export function confirmDialog(messageOrOptions: string | ConfirmOptions): Promise<boolean> {
  const options: ConfirmOptions =
    typeof messageOrOptions === 'string' ? { message: messageOrOptions } : messageOrOptions
  const message = String(options.message || '').trim()
  if (!message) return Promise.resolve(false)

  return new Promise<boolean>((resolve) => {
    queue.push({
      id: `c-${Date.now()}-${++seq}`,
      title: options.title || '请确认',
      message,
      confirmText: options.confirmText || '确定',
      cancelText: options.cancelText || '取消',
      danger: Boolean(options.danger),
      resolve,
    })
    openNext()
  })
}

function ConfirmDialog({ req }: { req: ConfirmRequest }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        finish(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [req.id])

  return (
    <div
      className="confirm-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) finish(false)
      }}
    >
      <div className="modal-card card confirm-card" role="alertdialog" aria-modal="true" aria-labelledby={`confirm-title-${req.id}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3 id={`confirm-title-${req.id}`}>{req.title}</h3>
        </div>
        <div className="modal-body">
          <p className="confirm-msg">{req.message}</p>
          <div className="modal-actions">
            <button type="button" className="btn ghost" onClick={() => finish(false)}>
              {req.cancelText}
            </button>
            <button
              type="button"
              className={req.danger ? 'btn danger' : 'btn'}
              autoFocus
              onClick={() => finish(true)}
            >
              {req.confirmText}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export function ConfirmHost() {
  const req = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  if (!req) return null
  return <ConfirmDialog req={req} />
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <ConfirmHost />
    </>
  )
}
