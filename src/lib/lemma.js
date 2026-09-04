// 导入词典数据（从全局变量）
// dict-data.js 定义了 window.RU_DICT
// dict-full.js 定义了 window.RU_DICT_FULL
export const RU_DICT = typeof window !== 'undefined' ? (window.RU_DICT || {}) : {}
export const RU_DICT_FULL = typeof window !== 'undefined' ? (window.RU_DICT_FULL || {}) : {}

// 标准化词形：去掉前后标点、转小写
export function normWord(word) {
  return (word || '')
    .replace(/^[«"'(]+|[»"').,;:!?…]+$/g, '')
    .toLowerCase()
    .trim()
}

// 在词典中查找 lemma（原始形式）
export function findLemma(word) {
  const w = normWord(word)
  if (!w) return null
  // 简版词典
  if (RU_DICT[w]) return w
  // 全词典
  if (RU_DICT_FULL[w]) return w
  return null
}

// 获取词条的中文翻译
export function getZh(word) {
  const lemma = findLemma(word)
  if (!lemma) return null
  if (RU_DICT[lemma]) return RU_DICT[lemma].z
  if (RU_DICT_FULL[lemma]) return RU_DICT_FULL[lemma].z || RU_DICT_FULL[lemma].e || null
  return null
}

// 获取词性标签
export function getPos(word) {
  const lemma = findLemma(word)
  if (!lemma) return null
  if (RU_DICT[lemma]) return RU_DICT[lemma].p
  if (RU_DICT_FULL[lemma]) return RU_DICT_FULL[lemma].p || null
  return null
}

// 获取完整词条信息（用于词典弹窗）
export function getEntry(word) {
  const lemma = findLemma(word)
  if (!lemma) return null
  // 优先全词典（含变格/变位）
  if (RU_DICT_FULL[lemma]) return { lemma, ...RU_DICT_FULL[lemma], source: 'full' }
  if (RU_DICT[lemma]) return { lemma, ...RU_DICT[lemma], source: 'basic' }
  return null
}

// 词性中文标签
export function posLabel(p) {
  const map = {
    '代': '代词', '疑': '疑问词', '疑/连': '疑问/连词', '数': '数词', '数/形': '数/形容词',
    '动': '动词', '动·未': '动词（未完成体）', '动·完': '动词（完成体）',
    '名·阳': '名词（阳性）', '名·阴': '名词（阴性）', '名·中': '名词（中性）', '名': '名词',
    '副/名': '副词/名词', '形': '形容词',
  }
  return map[p] || p
}

// AI 助教提问：这是什么格？为什么用这个语法？
export async function askAIGrammar(word, lemma, entry, settings) {
  const q = word || lemma || ''
  const out = { loading: true, html: '' }

  const messages = [
    { role: 'system', content: '你是专业的俄语助教，用中文讲解。用户查词典时点你，你必须按顺序回答三点：1) 这个形式是第几格（或什么时态/人称/数/性/体）2) 为什么这里要用这个格/这个语法 3) 这个语法在什么情况下可以使用。优先结合我给的变格变位表准确判断，不要臆测。用 Markdown，简洁、直接、有条理。' },
    { role: 'user', content: `用户查的词/形式：${q}${lemma ? '\n原形（词典词）：' + lemma : ''}${entry && entry.f ? '\n词性：' + posLabel(entry.p) + '\n变格/变位表：\n' + entryFormsText(entry) : ''}` }
  ]

  try {
    const res = await fetch('/api/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages })
    })
    const j = await res.json()
    if (j.ok) {
      out.loading = false
      out.html = j.content
    } else {
      out.loading = false
      out.html = `<div style="color:var(--danger)">${(j.error || '出错了').replace(/</g, '&lt;')}</div>`
    }
  } catch (err) {
    out.loading = false
    out.html = '<div style="color:var(--danger)">请求失败：请确认本地服务已启动且网络正常。</div>'
  }
  return out
}

// 从 entry 提取变格/变位文本
function entryFormsText(e) {
  if (!e || !e.f) return ''
  const f = e.f
  if (f.m) {
    const c = ['主格', '属格', '与格', '宾格', '工具格', '前置格']
    return c.map((x, i) => `${x}：${f.m[i]}（阳）/${f.f[i]}（阴）/${f.n[i]}（中）/${f.pl[i]}（复）`).join('；')
  }
  return ''
}
