// AI 断句服务：从 cues（字幕块）出发，调用 AI 完成断句 + 翻译
// 返回 { sentences, translations, understanding } 或 null（失败）

import { callAI } from './ai'
import { plainToSentences } from './srt'

// 软分块：把 cues 切成有 overlap 的块，避免在句子中间切断
function softChunkCues(cues, chunkSize = 20, overlap = 5) {
  const blocks = []
  let i = 0
  while (i < cues.length) {
    let wordCount = 0
    let j = i
    const collected = []
    while (j < cues.length && wordCount < chunkSize) {
      const ws = cues[j].text.trim().split(/\s+/).filter(Boolean)
      if (!ws.length) { j++; continue }
      collected.push(cues[j])
      wordCount += ws.length
      j++
    }
    if (!collected.length) break
    blocks.push({ cues: collected, start: i, end: j - 1 })
    if (j >= cues.length) break
    let back = 0, k = j - 1
    while (k > i && back < overlap) {
      const ws = cues[k].text.trim().split(/\s+/).filter(Boolean)
      back += ws.length
      k--
    }
    i = Math.max(i + 1, k + 1)
  }
  return blocks
}

function normWord(w) {
  return (w || '').toLowerCase().replace(/[.,!?…;:—\-–"«»()'’]/g, '').trim()
}

const SYS_BASE = `Ты — русский языковой эксперт. Твоя задача — разбить текст на естественные предложения.

Важно:
- Заголовки (отдельные строки, короткие фразы) НЕ являются субтитрами — игнорируй их.
- Не добавляй, не удаляй и не меняй ни одного слова.
- Вставляй только знаки препинания (, . ! ? …).
- Каждое предложение должно быть завершающим (оканчиваться на . ! ? …).
- Не объединяй разные предложения в одно — лучше разбить, чем соединить.
- Строго output только JSON: {"sentences":["Предложение 1.","Предложение 2?","Предложение 3."],"translations":["句子1。","句子2？","句子3。"]}`

function sysWithFeedback(fb, prev) {
  let t = SYS_BASE + `\n\nОбратная связь от пользователя: ${fb}\n`
  if (prev && prev.length) t += `\nПредыдущий вывод: ${prev.map((x, i) => x).join(' | ')}\n`
  return t
}

function validate(parsed, origWords) {
  if (!parsed || !parsed.sentences || !parsed.sentences.length) return { ok: false, reason: '空输出' }
  const outSeq = parsed.sentences.join(' ').trim().split(/\s+/).filter(Boolean).map(normWord)
  const inSeq = origWords.map(normWord)
  if (outSeq.length !== inSeq.length) return { ok: false, reason: '词数不符：原文' + inSeq.length + '，输出' + outSeq.length }
  for (let i = 0; i < inSeq.length; i++) if (outSeq[i] !== inSeq[i]) return { ok: false, reason: '第' + (i + 1) + '词不符' }
  return { ok: true }
}

// 解析纯文本：用 plainToSentences 兜底
async function aiSegmentFromPlain(text, feedback, settings) {
  const sents = plainToSentences(text)
  if (!settings.apiKey || !sents.length) {
    return { sentences: sents, translations: [], understanding: null }
  }
  // 简化版：直接调一次 AI 让它断句 + 翻译
  const messages = [
    { role: 'system', content: SYS_BASE + (feedback ? `\n\nОбратная связь от пользователя: ${feedback}` : '') },
    { role: 'user', content: '原文（无标点）：\n' + sents.map(s => s.text).join(' ') }
  ]
  try {
    const content = await callAI(messages)
    const parsed = parseResult(content)
    if (parsed && parsed.sentences && parsed.sentences.length) {
      const v = validate({ sentences: parsed.sentences }, sents.map(s => s.text).join(' ').trim().split(/\s+/))
      if (v.ok) {
        const translations = (parsed.translations || []).slice()
        while (translations.length < parsed.sentences.length) translations.push('')
        return { sentences: parsed.sentences.map(t => ({ text: t })), translations, understanding: parsed.understanding || null }
      }
    }
  } catch (e) {}
  return { sentences: sents, translations: [], understanding: null }
}

function parseResult(content) {
  let t = (content || '').trim()
  t = t.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '').trim()
  const a = t.indexOf('{'), b = t.lastIndexOf('}')
  if (a >= 0 && b > a) t = t.slice(a, b + 1)
  try { return JSON.parse(t) } catch (e) { return null }
}

// 从 cues 断句 + 翻译（带 overlap 处理）
export async function aiSegmentFromCues(cues, feedback, prevSentences, settings) {
  if (!settings.apiKey || !cues || !cues.length) return null
  const fullText = cues.map(c => c.text).join(' ')
  const inWords = fullText.trim().split(/\s+/).filter(Boolean)
  if (!inWords.length) return null

  const blocks = softChunkCues(cues, 20, 5)
  const allSentences = [], allTrans = []
  let block = [], blockTrans = []

  const pushGot = (got, skip) => {
    const gs = got.sentences, gt = got.translations || []
    for (let k = skip; k < gs.length; k++) {
      allSentences.push(gs[k])
      allTrans.push(gt[k] || '')
    }
  }
  const flushBlock = () => {
    for (let i = 0; i < block.length; i++) {
      allSentences.push(block[i])
      allTrans.push(blockTrans[i] || '')
    }
    block = []; blockTrans = []
  }

  for (let bi = 0; bi < blocks.length; bi++) {
    const blk = blocks[bi]
    const blockText = blk.cues.map(c => c.text).join(' ')
    const blockWords = blockText.trim().split(/\s+/).filter(Boolean)
    if (!blockWords.length) continue
    let got = null
    for (let attempt = 0; attempt <= 2 && !got; attempt++) {
      const prev = (prevSentences && prevSentences.length && attempt > 0) ? prevSentences.map(x => x.text) : null
      const sysMsg = sysWithFeedback(feedback || null, prev)
      const userMsg = '原文（无标点）：\n' + blockText + (feedback ? '\n用户反馈：' + feedback : '')
      try {
        const content = await callAI([{ role: 'system', content: sysMsg }, { role: 'user', content: userMsg }])
        const r = parseResult(content)
        if (r && r.sentences && r.sentences.length) {
          const v = validate({ sentences: r.sentences }, blockWords)
          if (v.ok) {
            got = r
            if (!got.translations || got.translations.length !== got.sentences.length) {
              got.translations = got.translations || []
              while (got.translations.length < got.sentences.length) got.translations.push('')
            }
          }
        }
      } catch (e) {}
    }
    if (!got) return null

    if (block.length) {
      // 找重叠区
      const tailWords = []
      for (let k = Math.max(0, block.length - 2); k < block.length; k++) {
        tailWords.push(...block[k].trim().split(/\s+/).filter(Boolean).map(normWord))
      }
      const headWords = []
      for (let k = 0; k < Math.min(2, got.sentences.length); k++) {
        headWords.push(...got.sentences[k].trim().split(/\s+/).filter(Boolean).map(normWord))
      }
      let overlapCount = 0
      const maxL = Math.min(tailWords.length, headWords.length, 8)
      for (let L = maxL; L >= 1; L--) {
        let ok = true
        for (let i = 0; i < L; i++) {
          if (tailWords[tailWords.length - L + i] !== headWords[i]) { ok = false; break }
        }
        if (ok) { overlapCount = L; break }
      }
      if (overlapCount > 0) {
        let skip = 0, cnt = 0
        for (const s of got.sentences) {
          const w = s.trim().split(/\s+/).filter(Boolean).length
          if (cnt + w <= overlapCount) { cnt += w; skip++ } else break
        }
        pushGot(got, skip)
      } else {
        flushBlock()
        pushGot(got, 0)
      }
    } else {
      // 第一块：保留最后一句作为下一块的重叠区
      const last = got.sentences[got.sentences.length - 1]
      const lastT = got.translations ? got.translations[got.translations.length - 1] : ''
      pushGot(got, 0)
      allSentences.pop(); allTrans.pop()
      block = last ? [last] : []
      blockTrans = lastT ? [lastT] : []
    }
  }
  flushBlock()

  if (!allSentences.length) return null
  const finalWords = allSentences.join(' ').trim().split(/\s+/).filter(Boolean).map(normWord)
  const inSeq = inWords.map(normWord)
  if (finalWords.length !== inSeq.length) return null
  for (let i = 0; i < inSeq.length; i++) if (finalWords[i] !== inSeq[i]) return null

  return {
    sentences: allSentences.map(t => ({ text: t, start: 0, end: 0 })),
    translations: allTrans,
    understanding: null
  }
}

export { aiSegmentFromPlain }