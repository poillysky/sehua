/**
 * iOS「主屏幕 / 独立全屏」检测。
 *
 * Safari 标签页：有 URL 栏与底栏，safe-area 通常很小（系统已挡刘海）。
 * 独立全屏（Add to Home Screen / display-mode:standalone）：
 *   无浏览器铬，black-translucent 下内容会伸到状态栏后，
 *   env(safe-area-inset-*) 为真实硬件 inset（顶约 47–59，底约 34）。
 *
 * 优先 navigator.standalone（iOS 可靠）；display-mode 作补充（部分机型不可靠）。
 */
function isIosPwa(): boolean {
  try {
    if (window.navigator.standalone === true) return true
    if (typeof window.matchMedia !== 'function') return false
    return (
      window.matchMedia('(display-mode: standalone)').matches ||
      window.matchMedia('(display-mode: fullscreen)').matches ||
      window.matchMedia('(display-mode: minimal-ui)').matches
    )
  } catch {
    return false
  }
}

export function applyIosPwaClass(): boolean {
  const on = isIosPwa()
  document.documentElement.classList.toggle('ios-pwa', on)
  return on
}

export function initIosPwaDetection(): () => void {
  applyIosPwaClass()
  const onChange = () => applyIosPwaClass()
  const mq =
    typeof window.matchMedia === 'function' ? window.matchMedia('(display-mode: standalone)') : null
  if (mq) {
    if (mq.addEventListener) mq.addEventListener('change', onChange)
    else mq.addListener(onChange)
  }
  window.addEventListener('orientationchange', onChange)
  return () => {
    if (mq) {
      if (mq.removeEventListener) mq.removeEventListener('change', onChange)
      else mq.removeListener(onChange)
    }
    window.removeEventListener('orientationchange', onChange)
  }
}
