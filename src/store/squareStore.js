import { create } from 'zustand'
import { squareItems } from '../data/squareLibrary'

export const useSquareStore = create(() => ({
  items() {
    return squareItems
  },

  getItem(id) {
    return squareItems.find(x => x.id === id) || null
  },
}))
