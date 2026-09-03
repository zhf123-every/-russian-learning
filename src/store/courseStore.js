import { create } from 'zustand'
import { loadLS, saveLS, LS } from '../lib/persistence'
import { findVideo, getLevelVideos, LEVELS } from '../data/courseLibrary'
import { videoScore, levelMastery, isLevelUnlocked as _unlock, isVideoUnlocked as _vUnlock } from '../lib/scoring'

function levelIds() {
  const m = {}
  for (const l of LEVELS) m[l] = getLevelVideos(l).map(x => x.video.id)
  return m
}

export const useCourseStore = create((set, get) => ({
  progress: loadLS(LS.progress, {}),
  recent: loadLS(LS.recent, []),
  materials: loadLS(LS.materials, []),

  getVideo(videoId) {
    if (videoId && videoId.startsWith('custom_')) {
      return get().materials.find(m => m.id === videoId) || null
    }
    const found = findVideo(videoId)
    return found ? found.video : null
  },

  pushRecent(videoId) {
    const now = Date.now()
    const recent = [{ videoId, updatedAt: now }, ...get().recent.filter(r => r.videoId !== videoId)].slice(0, 10)
    saveLS(LS.recent, recent)
    set({ recent })
  },

  recordSentenceScore(videoId, sid, patch) {
    set(s => {
      const v = s.progress[videoId] || { done: false, score: null, sentenceScores: {}, lastIndex: 0 }
      const next = {
        ...s.progress,
        [videoId]: {
          ...v,
          sentenceScores: { ...v.sentenceScores, [sid]: { ...v.sentenceScores[sid], ...patch } },
          lastIndex: sid,
          updatedAt: Date.now(),
        },
      }
      saveLS(LS.progress, next)
      return { progress: next }
    })
  },

  submitVideo(videoId) {
    const v = get().progress[videoId]
    if (!v) return 0
    const score = videoScore(v.sentenceScores)
    const next = { ...get().progress, [videoId]: { ...v, done: true, score } }
    saveLS(LS.progress, next)
    set({ progress: next })
    return score
  },

  resetLevel(level) {
    const ids = getLevelVideos(level).map(x => x.video.id)
    const next = { ...get().progress }
    for (const id of ids) delete next[id]
    saveLS(LS.progress, next)
    set({ progress: next })
  },

  addMaterial(material) {
    const materials = [material, ...get().materials]
    saveLS(LS.materials, materials)
    set({ materials })
  },

  levelIds() { return levelIds() },
  levelMastery(level) { return levelMastery(levelIds()[level], get().progress) },
  isLevelUnlocked(level) { return _unlock(level, get().progress, levelIds()) },
  isVideoUnlocked(level, idx) { return _vUnlock(level, idx, get().progress, levelIds()) },
}))
