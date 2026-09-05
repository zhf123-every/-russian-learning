import { create } from 'zustand'
import { loadLS, saveLS } from '../lib/persistence'

const LS_SHANG = 'rlearn_v1_shang'
// 阶段定义（与 ShangMethod 页面一致，沿用 shangWenjieStage 字段）
export const STAGES = {
  LISTEN: 1,   // 阶段1 整体盲听
  DICTATE: 2,  // 阶段2 逐句盲听听写
  CORRECT: 3,  // 阶段3 对照精读纠错
  RECITE: 4,   // 阶段4 跟读模仿
  RECITE_OUT: 5 // 阶段5 脱稿背诵输出
}

export const useShangStore = create((set, get) => ({
  // videoId -> { stage: 1..5, dictations: {sid: {text, skipped, ok}}, reciteOk: {sid: bool}, finished: bool }
  progress: loadLS(LS_SHANG, {}),

  load(videoId) {
    return get().progress[videoId] || null
  },
  init(videoId) {
    const p = get().progress
    if (!p[videoId]) {
      const next = { ...p, [videoId]: { stage: STAGES.LISTEN, dictations: {}, reciteOk: {}, finished: false } }
      saveLS(LS_SHANG, next)
      set({ progress: next })
    }
  },
  setStage(videoId, stage) {
    const p = get().progress
    const cur = p[videoId] || { stage: STAGES.LISTEN, dictations: {}, reciteOk: {}, finished: false }
    const next = { ...p, [videoId]: { ...cur, stage } }
    saveLS(LS_SHANG, next)
    set({ progress: next })
  },
  setDictation(videoId, sid, patch) {
    const p = get().progress
    const cur = p[videoId] || { stage: STAGES.DICTATE, dictations: {}, reciteOk: {}, finished: false }
    const next = { ...p, [videoId]: { ...cur, dictations: { ...cur.dictations, [sid]: { ...(cur.dictations[sid] || {}), ...patch } } } }
    saveLS(LS_SHANG, next)
    set({ progress: next })
  },
  setReciteOk(videoId, sid, ok) {
    const p = get().progress
    const cur = p[videoId] || { stage: STAGES.RECITE, dictations: {}, reciteOk: {}, finished: false }
    const next = { ...p, [videoId]: { ...cur, reciteOk: { ...cur.reciteOk, [sid]: ok } } }
    saveLS(LS_SHANG, next)
    set({ progress: next })
  },
  finish(videoId) {
    const p = get().progress
    const cur = p[videoId] || { stage: STAGES.RECITE_OUT, dictations: {}, reciteOk: {}, finished: false }
    const next = { ...p, [videoId]: { ...cur, stage: STAGES.RECITE_OUT, finished: true } }
    saveLS(LS_SHANG, next)
    set({ progress: next })
  },
  reset(videoId) {
    const p = get().progress
    const next = { ...p, [videoId]: { stage: STAGES.LISTEN, dictations: {}, reciteOk: {}, finished: false } }
    saveLS(LS_SHANG, next)
    set({ progress: next })
  },
  isFinished(videoId) {
    return !!(get().progress[videoId] && get().progress[videoId].finished)
  }
}))