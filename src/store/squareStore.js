import { create } from 'zustand'
import { loadLS, saveLS } from '../lib/persistence'
import { squareItems } from '../data/squareLibrary'

const LS_SQUARE = 'rlearn_v1_square'

export const useSquareStore = create((set, get) => ({
  userItems: loadLS(LS_SQUARE, []),

  items() {
    return [...get().userItems, ...squareItems]
  },

  getItem(id) {
    return get().items().find(x => x.id === id) || null
  },

  addItem(item) {
    const userItems = [item, ...get().userItems]
    saveLS(LS_SQUARE, userItems)
    set({ userItems })
  },
}))
