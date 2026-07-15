export type ResourceRow = {
  id: string
  title: string
  board: string
  outcome: string
  result: 'magnet' | 'ed2k' | 'stub' | 'failed'
  time: string
  sourceUrl?: string
  description?: string
  password?: string
  links?: string[]
}

export const MOCK_RESOURCES: ResourceRow[] = [
  {
    id: '1',
    title: '【示例】有码高清合集（演示数据）',
    board: '高清中文字幕',
    outcome: '已提取主链',
    result: 'magnet',
    time: '2026-07-14 08:12',
    sourceUrl: 'https://www.sehuatang.net/thread-00000000-1-1.html',
    description: '【影片格式】：MP4\n【影片大小】：4.2GB',
    password: '',
    links: ['magnet:?xt=urn:btih:DEMOHASH000000000000000000000000000000'],
  },
  {
    id: '2',
    title: '【示例】原创 ed2k 资源（演示数据）',
    board: '原创 ed2k',
    outcome: '已提取主链',
    result: 'ed2k',
    time: '2026-07-14 07:55',
    description: '【解压密码】：demo',
    password: 'demo',
    links: ['ed2k://|file|demo.rar|123456|ABCDEF0123456789|/'],
  },
  {
    id: '3',
    title: '【示例】需回复可见（占位 stub）',
    board: '亚洲无码原创',
    outcome: '无下载链 · 占位入库',
    result: 'stub',
    time: '2026-07-13 22:40',
    description: '【reply_required】帖内暂无明文链接',
    links: [],
  },
]

export const MOCK_CRAWL = {
  enabled: false,
  running: false,
  lastRun: '尚未执行（演示）',
  boards: [
    { fid: '36', name: '亚洲无码原创', pending: 12, done: 340 },
    { fid: '37', name: '亚洲有码原创', pending: 3, done: 210 },
    { fid: '103', name: '高清中文字幕', pending: 8, done: 520 },
    { fid: '104', name: '素人有码', pending: 0, done: 88 },
    { fid: '95', name: '91 精品', pending: 5, done: 160 },
    { fid: '141', name: '原创 ed2k', pending: 2, done: 45 },
    { fid: '142', name: '转帖区', pending: 20, done: 90 },
  ],
  activity: [
    { t: '08:12:01', msg: '列表扫描 fid=103 第 1 页 · 入队 18 帖' },
    { t: '08:12:15', msg: '详情 tid=demo1 · magnet 入库' },
    { t: '08:12:22', msg: '详情 tid=demo2 · stub 占位' },
  ],
}

export const MOCK_DATA_OVERVIEW = {
  resources: 1284,
  sources: 1302,
  crawlPages: 4560,
  boards: 12,
}
