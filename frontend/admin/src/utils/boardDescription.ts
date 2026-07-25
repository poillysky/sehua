/** 与后端 parsers.content.BOARD_DESCRIPTION_PROFILES / 结构卡片字段对齐 */

const BT_FIDS = new Set(['2', '36', '37', '103', '107', '160', '104', '38', '151', '152', '39'])
const PW_2048_FIDS = new Set(['3', '318', '4', '5', '13', '15', '16', '18', '343', '195', '67'])

type Profile = {
  labels: string[]
  exclusive: string[][]
  /** 入库别名 → 展示键（兼容旧库用「资源名称」存 BT 帖） */
  aliases: Record<string, string>
}

const PW_2048_BT: Profile = {
  labels: [
    '影片名称',
    '中文片名',
    '影片格式',
    '是否有码',
    '影片时间',
    '影片时长',
    '影片大小',
    '发布时间',
    '分辨率',
    '作种期限',
    '有无水印',
    '资源名称',
    '资源类型',
    '资源数量',
    '下载方式',
  ],
  exclusive: [['影片时间', '影片时长']],
  aliases: {
    影片名稱: '影片名称',
    資源名稱: '资源名称',
    资源名: '资源名称',
    文件大小: '影片大小',
    资源大小: '影片大小',
    資源大小: '影片大小',
    影片容量: '影片大小',
    是否有碼: '是否有码',
    有无码: '是否有码',
    有無碼: '是否有码',
    影片時間: '影片时间',
    影片時長: '影片时长',
    發布時間: '发布时间',
    解析度: '分辨率',
    有無浮水印: '有无水印',
    有无第三方水印: '有无水印',
    下載方式: '下载方式',
    作種期限: '作种期限',
    种子期限: '作种期限',
    種子期限: '作种期限',
    圖片預覽: '图片预览',
    影片預覽: '影片预览',
    影片截圖: '影片截图',
  },
}

const PROFILES: Record<string, Profile> = {
  bt: {
    labels: ['影片名称', '出演女优', '影片容量', '影片大小', '是否有码', '影片格式', '影片码别', '解压密码'],
    exclusive: [['影片容量', '影片大小']],
    aliases: {
      资源名称: '影片名称',
      有无码: '是否有码',
      文件大小: '影片大小',
      资源大小: '影片大小',
      提取密码: '解压密码',
      资源密码: '解压密码',
    },
  },
  '95': {
    labels: ['资源名称', '资源类型', '资源大小', '是否有码', '有无第三方水印', '解压密码'],
    exclusive: [],
    aliases: {
      影片名称: '资源名称',
      影片格式: '资源类型',
      文件大小: '资源大小',
      影片容量: '资源大小',
      影片大小: '资源大小',
      有无码: '是否有码',
      影片码别: '是否有码',
      有无水印: '有无第三方水印',
      第三方水印: '有无第三方水印',
      提取密码: '解压密码',
      资源密码: '解压密码',
    },
  },
  '141': {
    labels: ['资源名称', '资源类型', '资源数量', '资源大小', '有无水印', '是否有码', '解压密码'],
    exclusive: [],
    aliases: {
      影片名称: '资源名称',
      文件大小: '资源大小',
      影片容量: '资源大小',
      影片大小: '资源大小',
      有无第三方水印: '有无水印',
      有无码: '是否有码',
      提取密码: '解压密码',
      资源密码: '解压密码',
    },
  },
  '142': {
    labels: ['资源名称', '影片名称', '文件大小', '影片大小', '是否有码', '解压密码'],
    exclusive: [
      ['资源名称', '影片名称'],
      ['文件大小', '影片大小'],
    ],
    aliases: {
      资源大小: '文件大小',
      影片容量: '影片大小',
      有无码: '是否有码',
      提取密码: '解压密码',
      资源密码: '解压密码',
    },
  },
  default: {
    labels: ['资源名称', '资源类型', '资源大小', '是否有码', '有无第三方水印', '解压密码'],
    exclusive: [],
    aliases: {
      影片名称: '资源名称',
      影片格式: '资源类型',
      文件大小: '资源大小',
      影片容量: '资源大小',
      影片大小: '资源大小',
      有无码: '是否有码',
      影片码别: '是否有码',
      有无水印: '有无第三方水印',
      第三方水印: '有无第三方水印',
      提取密码: '解压密码',
      资源密码: '解压密码',
    },
  },
}

for (const fid of PW_2048_FIDS) {
  PROFILES[fid] = PW_2048_BT
}

function profileForBoard(boardFid?: string): Profile {
  const raw = (boardFid || '').trim()
  const fid = raw.includes(':') ? raw.split(':')[0]! : raw
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
    const rawKey = m[1].trim()
    const val = m[2].trim()
    const key = profile.aliases[rawKey] || rawKey
    if (!allowed.has(key) || !val || byLabel.has(key)) continue
    // 统一成当前卡片标签名展示
    byLabel.set(key, `【${key}】：${val}`)
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
