import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import {
  fetchForumRules,
  parseForumThread,
  type ForumBoard,
  type ParseThreadResult,
} from '../api/forums'
import { toast } from '../ui/toast'

type ParseLink = {
  infohash?: string
  hash?: string
  filename?: string
  size?: number
  link?: string
}

type ParseAttachment = {
  name?: string
  kind?: string
  url?: string
}

type ParseData = ParseThreadResult & {
  input_url?: string
  fetch_url?: string
  desktop_url?: string
  url_converted?: boolean
  mobile_input?: boolean
  mobile_shell?: boolean
  interstitial?: boolean
  page_title?: string
  resource_name?: string
  description?: string
  actress?: string
  coded?: string
  watermark?: string
  file_size?: string
  resource_count?: string
  extract_password?: string
  board_fid?: string
  board_name?: string
  link_kind?: string
  login_required?: boolean
  access_denied?: boolean
  reply_required?: boolean
  attachment_source?: string
  attachment_denied?: boolean
  attachment_failed?: boolean
  attachment_downloaded?: boolean
  attachment_text_len?: number
  attachment_text_preview?: string
  body_magnet_count?: number
  body_ed2k_count?: number
  magnets?: ParseLink[]
  ed2k_links?: ParseLink[]
  attachments?: ParseAttachment[]
  preview_images?: string[]
  html_len?: number
  soft_browser_retried?: boolean
  fetch_mode?: string
  host?: string
  import_verdict_label?: string
  import_outcome?: string
  import_link_count?: number
}

function parseTestWarnings(data: ParseData): string[] {
  const warnings: string[] = []
  if (data.mobile_input) {
    warnings.push('已将手机端链接规范为桌面帖 URL 再抓取')
  } else if (data.url_converted) {
    warnings.push('已规范为桌面帖 URL 再抓取')
  }
  if (data.interstitial) warnings.push('站点软文拦截（名人名言页），非真实帖正文')
  if (data.mobile_shell) warnings.push('检测到手机版空壳页，已尝试转桌面链接重抓')
  if (data.login_required) warnings.push('帖子需要论坛登录')
  if (data.access_denied) warnings.push('阅读权限不足 / 访问受限')
  if (data.reply_required) warnings.push('帖子需要回复后才可见资源')
  if (data.attachment_denied) warnings.push('附件无下载权限')
  if (data.attachment_failed) warnings.push('附件下载失败')
  if (data.attachment_downloaded && !data.attachment_text_len && data.attachments?.length) {
    warnings.push('附件已下载但解压为空（可能缺少 unrar/7z，或附件非文本链接）')
  }
  if (!data.final_ed2k_count && !data.final_magnet_count) {
    warnings.push('未发现可入库的 ED2K 或 magnet 链接')
  }
  if (data.soft_browser_retried) {
    warnings.push('HTTP 遇软文/安全壳，已用浏览器整页重读')
  }
  return warnings
}

function verdictClass(verdict?: string) {
  if (verdict === 'import') return 'pt-verdict-import'
  if (verdict === 'stub') return 'pt-verdict-stub'
  if (verdict === 'interstitial') return 'pt-verdict-warn'
  return 'pt-verdict-failed'
}

function linkKindTag(kind?: string) {
  if (!kind) return null
  const k = kind.toLowerCase()
  if (k === 'magnet') return <span className="tag tag-magnet">magnet</span>
  if (k === 'ed2k') return <span className="tag tag-ed2k">ED2K</span>
  if (k === 'both' || k === 'mixed') return <span className="tag tag-active">双链</span>
  return <span className="tag tag-disabled">{kind}</span>
}

function LinkBlock({ title, items }: { title: string; items?: ParseLink[] }) {
  if (!items?.length) return null
  return (
    <section className="pt-block">
      <div className="pt-block-title">
        {title} <span className="pt-count">{items.length}</span>
      </div>
      {items.map((item) => (
        <div key={item.link || item.hash || item.infohash} className="pt-link">
          <div className="pt-link-name">{item.filename || item.infohash || item.hash || '链接'}</div>
          <code className="pt-link-uri">{item.link || ''}</code>
        </div>
      ))}
    </section>
  )
}

function ParseResultView({ data }: { data: ParseData }) {
  const warnings = parseTestWarnings(data)
  const title = data.title || data.page_title || '（无标题）'
  const resourceName = (data.resource_name || '').trim()
  const showResourceName = Boolean(resourceName && resourceName !== title.trim() && !title.includes(resourceName))
  const verdict = data.import_verdict || 'failed'
  const label = data.import_verdict_label || '异常标记'
  const count = data.import_link_count ?? 0
  const detail =
    verdict === 'import' && count > 0 ? `预计写入 ${count} 条资源` : data.import_outcome || ''

  const metaRows: Array<[string, string | number | undefined, boolean?]> = [
    showResourceName ? ['资源名称', resourceName, true] : null,
    ['资源数量', data.resource_count],
    ['文件大小', data.file_size],
    ['有无水印', data.watermark],
    ['有无码', data.coded],
    ['女优', data.actress],
    ['解压密码', data.extract_password, true],
    ['抓取 URL', data.fetch_url, true],
    ['桌面 URL', data.desktop_url, true],
    ['抓取模式', data.fetch_mode],
    ['附件来源', data.attachment_source],
  ].filter(Boolean) as Array<[string, string | number | undefined, boolean?]>

  const previewImages = (data.preview_images || [])
    .filter((src) => Boolean(src?.trim()) && !/static\/image\/filetype|smiley|avatar/i.test(src))
    .slice(0, 5)

  return (
    <div className="pt-result">
      <div className={`pt-verdict ${verdictClass(verdict)}`}>
        <span className="pt-verdict-label">{label}</span>
        <span className="pt-verdict-outcome">{detail}</span>
      </div>

      {warnings.length ? (
        <ul className="pt-warns">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}

      <header className="pt-hero">
        <h4 className="pt-title">{title}</h4>
        <div className="pt-tags">
          {data.board_name ? <span className="tag tag-active">{data.board_name}</span> : null}
          {data.board_fid ? <span className="tag tag-disabled">fid {data.board_fid}</span> : null}
          {linkKindTag(data.link_kind)}
          {data.mobile_input ? <span className="tag tag-stub">手机链接</span> : null}
          {data.url_converted ? <span className="tag tag-disabled">已转桌面</span> : null}
          <span className="tag tag-disabled">{Number(data.html_len || 0).toLocaleString()} B</span>
        </div>
        <div className="pt-stats">
          {(
            [
              ['ED2K', data.final_ed2k_count ?? 0],
              ['magnet', data.final_magnet_count ?? 0],
              ['正文ED2K', data.body_ed2k_count ?? 0],
              ['正文磁力', data.body_magnet_count ?? 0],
              ['附件', data.attachments?.length ?? 0],
              ['解压密码', data.extract_password ? data.extract_password : '无'],
            ] as const
          ).map(([lbl, val]) => (
            <span key={lbl} className="pt-stat">
              <em>{lbl}</em>
              <strong>{val}</strong>
            </span>
          ))}
        </div>
      </header>

      {metaRows.length ? (
        <dl className="pt-meta">
          {metaRows
            .filter(([, val]) => val !== undefined && val !== null && String(val).trim() !== '')
            .map(([lbl, val, full]) => (
              <div key={lbl} className={`pt-row${full ? ' full' : ''}`}>
                <dt>{lbl}</dt>
                <dd className={lbl === '解压密码' ? 'mono' : undefined}>{String(val)}</dd>
              </div>
            ))}
        </dl>
      ) : null}

      {data.description ? (
        <section className="pt-block">
          <div className="pt-block-title">简介</div>
          <pre className="pt-pre">{data.description}</pre>
        </section>
      ) : null}

      {previewImages.length ? (
        <section className="pt-block">
          <div className="pt-block-title">
            预览图 <span className="pt-count">{previewImages.length}</span>
          </div>
          <ul className="pt-preview-grid">
            {previewImages.map((src) => (
              <li key={src}>
                <a href={src} target="_blank" rel="noreferrer">
                  <img
                    src={src}
                    alt=""
                    loading="lazy"
                    onError={(e) => {
                      const li = e.currentTarget.closest('li')
                      if (li instanceof HTMLElement) li.hidden = true
                    }}
                  />
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.attachments?.length ? (
        <section className="pt-block">
          <div className="pt-block-title">
            附件 <span className="pt-count">{data.attachments.length}</span>
          </div>
          <div className="pt-chips">
            {data.attachments.map((a) => (
              <span key={`${a.kind}-${a.name}-${a.url}`} className="pt-chip">
                {a.kind || '?'} · {a.name || ''}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <LinkBlock title="ED2K 链接" items={data.ed2k_links} />
      <LinkBlock title="Magnet 链接" items={data.magnets} />

      {data.attachment_text_preview ? (
        <section className="pt-block">
          <div className="pt-block-title">附件解压预览</div>
          <pre className="pt-pre">{data.attachment_text_preview}</pre>
        </section>
      ) : null}
    </div>
  )
}

export function ParseTestPage() {
  const [forumId, setForumId] = useState('sehuatang')
  const [boards, setBoards] = useState<ForumBoard[]>([])
  const [url, setUrl] = useState('')
  const [fid, setFid] = useState('')
  const [proxy, setProxy] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('等待输入链接')
  const [statusTone, setStatusTone] = useState<'loading' | 'done' | 'warn' | ''>('')
  const [result, setResult] = useState<ParseData | null>(null)

  useEffect(() => {
    let cancelled = false
    void fetchForumRules()
      .then((data) => {
        if (cancelled) return
        const active = data.active_forum_id || data.site_crawler_forum_id || 'sehuatang'
        setForumId(active)
        const forum = data.forums?.find((f) => f.id === active) || data.forums?.[0]
        const cfg = data.forum_configs?.[active] || forum?.crawler_config
        const list = [...(forum?.boards || [])]
        // 解析测试只需板块级偏好，按 fid 去重
        const byFid = new Map<string, ForumBoard>()
        for (const b of list) {
          const fid = String(b.fid)
          if (!byFid.has(fid)) {
            byFid.set(fid, {
              ...b,
              name: b.board_name || b.name.split('-')[0] || b.name,
              key: fid,
              typeid: '',
            })
          }
        }
        const deduped = Array.from(byFid.values())
        deduped.sort((a, b) => (a.priority ?? 50) - (b.priority ?? 50) || a.name.localeCompare(b.name, 'zh-CN'))
        setBoards(deduped)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const threadUrl = url.trim()
    if (!threadUrl) {
      toast.warn('请输入帖子 URL')
      return
    }
    setBusy(true)
    setStatus('解析中…')
    setStatusTone('loading')
    setResult(null)
    try {
      const data = (await parseForumThread(forumId, {
        url: threadUrl,
        fid: fid.trim() || undefined,
        proxy: proxy.trim() || undefined,
      })) as ParseData
      setResult(data)
      const hasLinks = Boolean(data.final_ed2k_count || data.final_magnet_count)
      setStatus(hasLinks ? '解析完成' : '完成（无链接）')
      setStatusTone(hasLinks ? 'done' : 'warn')
    } catch (err) {
      setResult(null)
      setStatus('解析失败')
      setStatusTone('warn')
      toast.error(err instanceof Error ? err.message : '解析失败')
    } finally {
      setBusy(false)
    }
  }

  let resultBody: ReactNode
  if (busy) {
    resultBody = (
      <div className="parse-test-loading">
        <div className="parse-test-loading-spinner" aria-hidden />
        <p>浏览器过 18+ 后 HTTP 抓取正文，请稍候…</p>
      </div>
    )
  } else if (result) {
    resultBody = <ParseResultView data={result} />
  } else {
    resultBody = (
      <div className="parse-test-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
        <p className="parse-test-empty-copy">
          <span className="parse-test-hint-short">在上方输入帖子链接后开始解析</span>
          <span className="parse-test-hint-full">在左侧输入帖子链接，点击「开始解析」查看结果</span>
        </p>
      </div>
    )
  }

  return (
    <section className="page page-parse-test active">
      <aside className="parse-test-side">
        <div className="card parse-test-card">
          <div className="parse-test-card-head">
            <div>
              <h3>帖子解析测试</h3>
              <p className="hint parse-test-hint">
                <span className="parse-test-hint-short">支持桌面/手机链接，自动转桌面；默认不入库。</span>
                <span className="parse-test-hint-full">
                  支持桌面与手机端链接（自动转桌面）。浏览器过 18+ → HTTP 读正文，默认不入库。
                </span>
              </p>
            </div>
          </div>
          <form className="parse-test-form" onSubmit={(e) => void onSubmit(e)}>
            <label className="parse-test-field">
              <span className="lbl">帖子 URL</span>
              <textarea
                rows={2}
                required
                inputMode="url"
                autoCapitalize="off"
                autoCorrect="off"
                spellCheck={false}
                placeholder="粘贴帖子链接（桌面或手机端均可）"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={busy}
              />
            </label>
            <div className="parse-test-optional-row">
              <label className="parse-test-field">
                <span className="lbl">板块（可选）</span>
                <select value={fid} onChange={(e) => setFid(e.target.value)} disabled={busy}>
                  <option value="">自动识别（磁力/电驴均可）</option>
                  {boards.map((b) => {
                    const link =
                      b.primary_link === 'ed2k' ? '电驴' : b.primary_link === 'magnet' ? '磁力' : b.primary_link || ''
                    return (
                      <option key={b.fid} value={b.fid}>
                        {b.name}
                        {link ? ` · ${link}` : ''}
                        {`（${b.fid}）`}
                      </option>
                    )
                  })}
                </select>
              </label>
              <label className="parse-test-field">
                <span className="lbl">代理覆盖（可选）</span>
                <input
                  type="text"
                  placeholder="留空则用系统设置"
                  value={proxy}
                  onChange={(e) => setProxy(e.target.value)}
                  disabled={busy}
                />
              </label>
            </div>
            <div className="parse-test-actions">
              <button type="submit" className="btn primary block" disabled={busy}>
                {busy ? '解析中…' : '开始解析'}
              </button>
            </div>
          </form>
        </div>
      </aside>

      <div className="parse-test-main">
        <div className="card parse-test-card parse-test-output-card">
          <div className="parse-test-card-head">
            <div>
              <h3>解析结果</h3>
              <p className="hint">判定、链接与附件预览</p>
            </div>
            <span className={`parse-test-status${statusTone ? ` is-${statusTone}` : ''}`}>{status}</span>
          </div>
          <div className="parse-test-result">{resultBody}</div>
        </div>
      </div>
    </section>
  )
}
