// 解析 SRT/VTT 字幕文本，返回带时间戳的 cues
export function parseSubtitles(text) {
  const s = (text || '').replace(/\r\n/g, '\n').trim()
  const blocks = s.split(/\n{2,}/)
  const cues = []
  for (const b of blocks) {
    let block = b.trim()
    if (!block) continue
    if (/^(WEBVTT|Kind:|Language:|NOTE)/i.test(block)) continue
    const lines = block.split('\n').map(l => l.trim()).filter(Boolean)
    const tl = lines.find(l => l.includes('-->'))
    if (!tl) continue
    const parts = tl.split('-->')
    const start = parseTime(parts[0])
    const end = parseTime(parts[1] || '')
    if (start === null) continue
    const txt = lines.filter(l => !l.includes('-->') && !/^\d+$/.test(l)).join(' ').trim()
    if (txt) cues.push({ start, end: end === null ? start + 3 : end, text: cleanVtt(txt) })
  }
  return cues
}

function parseTime(t) {
  // 格式: HH:MM:SS,mmm 或 HH:MM:SS.mmm
  const m = t.trim().match(/^(\d+):(\d+):(\d+)[.,](\d+)$/)
  if (!m) return null
  const h = parseInt(m[1]), min = parseInt(m[2]), s = parseInt(m[3]), ms = parseInt(m[4])
  return h * 3600 + min * 60 + s + ms / (m[4].length === 3 ? 1000 : 100)
}

function cleanVtt(s) {
  return s.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim()
}

// 将 cues 断句为句子对象（含 start/end 时间戳）
// 规则：句末标点、cue 边界、超过 18 词强制切、< 2 词碎片合并到前句
export function cuesToSentences(cues) {
  if (!cues || cues.length === 0) return []
  const words = []
  cues.forEach(c => {
    const ws = c.text.trim().split(/\s+/).filter(Boolean)
    if (!ws.length) return
    const dur = c.end - c.start
    ws.forEach((w, i) => {
      words.push({
        w,
        s: c.start + dur * (i / Math.max(1, ws.length)),
        e: c.start + dur * ((i + 1) / Math.max(1, ws.length)),
        cueStart: c.start,
        cueEnd: c.end
      })
    })
  })
  if (!words.length) return []

  // 标记句末词
  const isEnd = new Array(words.length).fill(false)
  for (let i = 0; i < words.length; i++) {
    if (/[.!?…]$/.test(words[i].w)) isEnd[i] = true
  }
  // cue 边界 = 潜在句末
  for (let i = 1; i < words.length; i++) {
    if (words[i].cueStart !== words[i - 1].cueStart) isEnd[i - 1] = true
  }

  const out = []
  let cur = null
  const wc = s => s.trim().split(/\s+/).filter(Boolean).length
  const MAXW = 18, MINW = 2
  const push = () => {
    if (!cur) return
    out.push({ start: cur.start, end: cur.end, text: cur.text.trim() })
    cur = null
  }

  for (let i = 0; i < words.length; i++) {
    const w = words[i]
    if (!cur) cur = { start: w.s, end: w.e, text: w.w }
    else { cur.end = w.e; cur.text += ' ' + w.w }

    const atEnd = isEnd[i]
    const tooLong = wc(cur.text) >= MAXW
    const lastOne = (i === words.length - 1)

    if (atEnd || tooLong || lastOne) {
      push()
    }
  }
  if (cur) push()

  // 合并过短碎片
  const merged = []
  for (const s of out) {
    const wc2 = s.text.trim().split(/\s+/).filter(Boolean).length
    if (wc2 < MINW && merged.length) {
      const p = merged[merged.length - 1]
      p.text = (p.text + ' ' + s.text).trim()
      p.end = s.end
    } else {
      merged.push(s)
    }
  }
  return merged.filter(s => s.text.trim())
}

// 无字幕时，从纯文本断句
export function plainToSentences(text) {
  const lines = (text || '').trim().split('\n').map(l => l.trim()).filter(Boolean)
  // 过滤短标题行（< 4 词的非最后一行）
  const filtered = lines.filter(l => {
    const words = l.split(/\s+/).filter(Boolean)
    if (words.length < 4 && lines.indexOf(l) !== lines.length - 1) return false
    return true
  })
  const cleaned = filtered.join(' ')

  // 有标点时按标点断句
  const parts = cleaned.match(/[^.!?…\n]+[.!?…]+|[^.!?…\n]+$/g)
  if (parts && parts.length > 1) {
    return parts.map(t => t.trim()).filter(Boolean).map((t, i) => ({
      start: i * 4, end: i * 4 + 4, text: t
    }))
  }

  // 无标点：按俄语语法信号智能断句
  const words = cleaned.trim().split(/\s+/).filter(Boolean)
  if (words.length <= 1) return words.map(w => ({ start: 0, end: 4, text: w }))

  const out = []
  let cur = []
  const isEndWord = w => /[.!?…]$/.test(w)
  const isClauseStart = (w, next, idx) => {
    const low = w.toLowerCase()
    // 疑问词
    if (/^(что|как|где|почему|зачем|куда|ли|разве|неужели)$/.test(low)) return true
    // 语气词独立成句
    if (/^(да|нет|ну|ладно|хорошо|давай|пожалуйста|вот)$/.test(low)) return true
    // 代词主语 + 下一词是动词变位
    if (/^(я|ты|мы|вы|они|он|она|оно)$/.test(low) && next) {
      const nl = next.toLowerCase()
      if (/(ет|ют|ю|ёшь|ёте|ешь|ете|ется|ются|ал|ла|ло|ли|ть|ти|лся|лась|лось|ались)$/i.test(nl)) return true
    }
    // 新主语代词（句中位置较后）
    if (/^(я|ты|мы|вы|они|он|она|оно)$/.test(low) && idx >= 4) return true
    // 对立连词
    if (/^(но|однако|зато)$/.test(low)) return true
    // 从属连词
    if (/^(чтобы|если|когда|хотя|потому|поэтому|так как|перед тем как|после того как)$/.test(low)) return true
    return false
  }

  const MAXW = 18
  for (let i = 0; i < words.length; i++) {
    const w = words[i]
    const next = words[i + 1]
    const atNewStart = (i > 0 && cur.length >= 2 && isClauseStart(w, next, i))
    if (atNewStart) {
      out.push({ start: out.length * 4, end: out.length * 4 + 4, text: cur.join(' ') })
      cur = []
    }
    cur.push(w)
    let shouldCut = false
    if (isEndWord(w)) shouldCut = true
    else if (cur.length >= MAXW) shouldCut = true
    if (shouldCut) {
      out.push({ start: out.length * 4, end: out.length * 4 + 4, text: cur.join(' ') })
      cur = []
    }
  }
  if (cur.length) out.push({ start: out.length * 4, end: out.length * 4 + 4, text: cur.join(' ') })

  // 合并过短碎片
  const merged = []
  for (const s of out) {
    const wc2 = s.text.trim().split(/\s+/).filter(Boolean).length
    if (wc2 < 2 && merged.length) {
      const p = merged[merged.length - 1]
      p.text = (p.text + ' ' + s.text).trim()
      p.end = s.end
    } else {
      merged.push(s)
    }
  }
  return merged.filter(s => s.text.trim())
}

// 统一入口：有字幕用 cues，无字幕用 plainToSentences
export function parseTextToSentences(text) {
  const cues = parseSubtitles(text)
  if (cues.length) return { sentences: cuesToSentences(cues), hasTimestamps: true }
  return { sentences: plainToSentences(text), hasTimestamps: false }
}

// 调用后端 /api/segment 用 razdel 断句（无标点时更准确）
export async function ruSegment(text) {
  try {
    const r = await fetch('/api/segment', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    })
    const j = await r.json()
    if (j.ok && Array.isArray(j.sentences)) return j.sentences
    return null
  } catch (e) {
    return null
  }
}

// 标准化文本（用于比较、查找）
export function norm(s) {
  return (s || '')
    .toLowerCase()
    .replace(/[.,!?…;:—\-–"«»()'']/g, ' ')
    .replace(/[̀́̆̈]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

// 从词库数据中查找 lemma
export function findLemma(word, dictData, dictFull) {
  const w = word.replace(/^[«"'(]+|[»"').,;:!?…]+$/g, '').toLowerCase()
  // 简版词典：lemma -> zh
  if (dictData && dictData[w]) return w
  // 全词典：lemma -> { p, g, ... }
  if (dictFull && dictFull[w]) return w
  return null
}