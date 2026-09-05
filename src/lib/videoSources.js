// 视频源列表：投稿/自定义素材共用。
// 后端统一走 yt-dlp（resolve_stream / fetch_subs），这些平台都原生支持，
// 这里的 key 只用于前端下拉展示与占位提示。
export const VIDEO_SOURCES = [
  { key: 'youtube', label: 'YouTube', placeholder: 'https://www.youtube.com/watch?v=...' },
  { key: 'bilibili', label: '哔哩哔哩 B站', placeholder: 'https://www.bilibili.com/video/BV...' },
  { key: 'douyin', label: '抖音', placeholder: 'https://www.douyin.com/video/...' },
  { key: 'xiaohongshu', label: '小红书', placeholder: 'https://www.xiaohongshu.com/explore/...' },
  { key: 'acfun', label: 'ACFUN', placeholder: 'https://www.acfun.cn/v/ac...' },
  { key: 'cctv', label: '央视网', placeholder: 'https://tv.cctv.com/...' },
]

export function sourceLabel(key) {
  const s = VIDEO_SOURCES.find(x => x.key === key)
  return s ? s.label : (key || '')
}

export function sourcePlaceholder(key) {
  const s = VIDEO_SOURCES.find(x => x.key === key)
  return s ? s.placeholder : '粘贴视频链接…'
}
