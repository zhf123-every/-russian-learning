import { create } from 'zustand'
import { loadLS, saveLS, LS } from '../lib/persistence'
import { newCard, review, isDue, serializeCard, deserializeCard } from '../lib/fsrs'

function load() {
  return loadLS(LS.vocab, []).map(c => ({ ...c, fsrs: deserializeCard(c.fsrs) }))
}

export const useVocabStore = create((set, get) => ({
  cards: load(),

  addWord({ word, lemma, chinese, source }) {
    const card = {
      id: 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      word, lemma, chinese, source,
      fsrs: newCard(),
      createdAt: Date.now(),
    }
    const cards = [card, ...get().cards]
    saveLS(LS.vocab, cards.map(c => ({ ...c, fsrs: serializeCard(c.fsrs) })))
    set({ cards })
  },

  review(cardId, rating) {
    set(s => {
      const cards = s.cards.map(c => c.id === cardId ? { ...c, fsrs: review(c.fsrs, rating) } : c)
      saveLS(LS.vocab, cards.map(c => ({ ...c, fsrs: serializeCard(c.fsrs) })))
      return { cards }
    })
  },

  dueCards() {
    const now = Date.now()
    return get().cards.filter(c => isDue(c.fsrs, now))
  },
}))
