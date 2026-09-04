import { create } from 'zustand'
import { loadLS, saveLS } from '../lib/persistence'
import { squareItems } from '../data/squareLibrary'

const LS_SQUARE = 'rlearn_v1_square'

export const useSquareStore = create((set, get) => ({
  userItems: loadLS(LS_SQUARE, []),
  serverItems: [],

  items() {
    const seen = new Set()
    const out = []
    for (const x of [...get().serverItems, ...get().userItems, ...squareItems]) {
      if (!seen.has(x.id)) { seen.add(x.id); out.push(x) }
    }
    return out
  },

  getItem(id) {
    return get().items().find(x => x.id === id) || null
  },

  addItem(item) {
    const userItems = [item, ...get().userItems]
    saveLS(LS_SQUARE, userItems)
    set({ userItems })
  },

  async fetchServer() {
    try {
      const r = await fetch('/api/square/list')
      const j = await r.json()
      if (j.ok && Array.isArray(j.list)) set({ serverItems: j.list })
    } catch (e) {
      /* 后端不可用则忽略，保留内置 + 本地 */
    }
  },

  async submitItem(item) {
    const r = await fetch('/api/square/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(item),
    })
    const j = await r.json()
    if (!j.ok) throw new Error(j.error || '投稿失败')
    set(s => ({ serverItems: [item, ...s.serverItems] }))
    return j
  },
}))
