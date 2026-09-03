import { create } from 'zustand'

export const useSessionStore = create((set) => ({
  videoId: null,
  curIdx: 0,
  stage: 'listen',
  revealed: false,
  sentenceScores: {},
  open(videoId) {
    set({ videoId, curIdx: 0, stage: 'listen', revealed: false, sentenceScores: {} })
  },
  setIdx(curIdx) { set({ curIdx }) },
  setStage(stage) { set({ stage }) },
  toggleRevealed() { set(s => ({ revealed: !s.revealed })) },
  setSentenceScore(sid, patch) {
    set(s => ({ sentenceScores: { ...s.sentenceScores, [sid]: { ...s.sentenceScores[sid], ...patch } } }))
  },
}))
