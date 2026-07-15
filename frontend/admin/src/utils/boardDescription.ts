/** 与后端 parsers.content.BOARD_DESCRIPTION_PROFILES / 结构卡片字段对齐 */

const BT_FIDS = new Set(['2', '36', '37', '103', '107', '160', '104', '38', '151', '152', '39'])

type Profile = {
  labels: string[]
  exclusive: string[][]
}

const PROFILES: Record<string, Profile> = {
  bt: {
    labels: ['影片名称', '出演女优', '影片容量', '影片大小', '是否有码', '影片格式', '影片码别', '解压密码'],
    exclusive: [['影片容量', '影片大小']],
  },
  '95': {
    labels: ['资源名称', '资源类型', '资源大小', '是否有码', '有无第三方水印', '解压密码'],
    exclusive: [],
  },
  '141': {
    labels: ['资源名称', '资源类型', '资源数量', '资源大小', '有无水印', '是否有码', '解压密码'],
    exclusive: [],
  },
  '142': {
    labels: ['资源名称', '影片名称', '文件大小', '影片大小', '是否有码', '解压密码'],
    exclusive: [
      ['资源名称', '影片名称'],
      ['文件大小', '影片大小'],
    ],
  },
  default: {
    labels: ['资源名称', '资源类型', '资源大小', '是否有码', '有无第三方水印', '解压密码'],
    exclusive: [],
  },
}

function profileForBoard(boardFid?: string): Profile {
  const fid = (boardFid || '').trim()
  if (PROFILES[fid]) return PROFILES[fid]
  if (BT_FIDS.has(fid)) return PROFILES.bt
  return PROFILES.default
}

/** 详情「描述」按板块结构卡片过滤展示（兼容旧库脏数据） */
export function formatBoardDescription(description: string | undefined, boardFid?: string): string {
  const raw = (description || '').trim()
  if (!raw) return ''
  const profile = profileForBoard(boardFid)
  const allowed = new Set(profile.labels)
  const byLabel = new Map<string, string>()
  for (const line of raw.split(/\r?\n/)) {
    const m = line.match(/^【\s*([^】]+?)\s*】\s*[:：]?\s*(.*)$/)
    if (!m) continue
    const key = m[1].trim()
    const val = m[2].trim()
    if (!allowed.has(key) || !val || byLabel.has(key)) continue
    byLabel.set(key, line.trim())
  }
  for (const group of profile.exclusive) {
    const hit = group.find((k) => byLabel.has(k))
    if (hit) {
      for (const k of group) {
        if (k !== hit) byLabel.delete(k)
      }
    }
  }
  return profile.labels.map((k) => byLabel.get(k)).filter(Boolean).join('\n')
}
