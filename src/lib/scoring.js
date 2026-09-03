import { LEVELS } from '../data/courseLibrary'

export const LEVEL_PASS = 60

export function norm(s) {
  return (s || '')
    .toLowerCase()
    .replace(/[.,!?…;:—\-–"«»()'’]/g, ' ')
    .replace(/[̀́̆̈]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function words(s) { return norm(s).split(' ').filter(Boolean) }

function lcs(a, b) {
  const m = a.length, n = b.length
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--)
    for (let j = n - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  return dp
}

export function dictation(input, target) {
  const tw = words(target), iw = words(input)
  if (!tw.length) return { score: 0, diff: [] }
  const dp = lcs(iw, tw)
  const diff = []
  let i = 0, j = 0
  while (j < tw.length) {
    if (i < iw.length && iw[i] === tw[j]) { diff.push({ word: tw[j], ok: true }); i++; j++ }
    else if (i < iw.length && dp[i + 1][j] >= dp[i][j + 1]) { diff.push({ word: iw[i], ok: false }); i++ }
    else { diff.push({ word: tw[j], ok: false }); j++ }
  }
  const okCount = diff.filter(d => d.ok).length
  return { score: Math.round((okCount / tw.length) * 100), diff }
}

export function selfRate(g) { return [0, 35, 70, 100][g] ?? 0 }

export function sentenceMastery(scores) {
  const vals = [scores?.dictate, scores?.recite].filter(v => typeof v === 'number')
  if (!vals.length) return null
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
}

export function videoScore(sentenceScores) {
  const vals = Object.values(sentenceScores || {}).map(sentenceMastery).filter(v => v != null)
  if (!vals.length) return 0
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
}

// videoIds: 该级全部视频 id（按顺序）；progress: courseStore 的 progress
export function levelMastery(videoIds, progress) {
  if (!videoIds.length) return 0
  let sum = 0
  for (const id of videoIds) {
    const p = progress[id]
    if (p && p.done && typeof p.score === 'number') sum += p.score
  }
  return Math.round(sum / videoIds.length)
}

// levelIds: { A1: [...], A2: [...], ... }（调用方用 getLevelVideos 构建）
export function isLevelUnlocked(level, progress, levelIds) {
  const order = LEVELS
  const idx = order.indexOf(level)
  if (idx <= 0) return true
  return levelMastery(levelIds[order[idx - 1]], progress) >= LEVEL_PASS
}

export function isVideoUnlocked(level, idx, progress, levelIds) {
  if (!isLevelUnlocked(level, progress, levelIds)) return false
  if (idx === 0) return true
  const prevId = levelIds[level][idx - 1]
  return !!(progress[prevId] && progress[prevId].done)
}
