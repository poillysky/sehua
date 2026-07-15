/** Site-wide inbound resource format (not per-forum). */
export const SITE_RESOURCE_FORMAT = [
  { no: 1, name: '标题', note: '' },
  { no: 2, name: '文件大小', note: '帖子内容 → 标题 → 资源链接，命中即停' },
  { no: 3, name: '预览图', note: '最多 5 张' },
  { no: 4, name: '来源论坛名', note: '' },
  { no: 5, name: '来源板块名', note: '' },
  { no: 6, name: 'magnet 或 ED2K 链接', note: '' },
  { no: 7, name: '帖子原链接', note: '' },
  { no: 8, name: '资源解压密码', note: '如有则解析入库，无则留空' },
] as const
