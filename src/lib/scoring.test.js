import { describe, it, expect } from 'vitest'
import {
  norm, dictation, selfRate, sentenceMastery, videoScore,
  levelMastery, isLevelUnlocked, isVideoUnlocked, LEVEL_PASS
} from './scoring'

describe('norm', () => {
  it('strips punctuation, accents, lowercases, collapses spaces', () => {
    expect(norm('Здра́вствуйте!')).toBe('здравствуйте')
    expect(norm('  Как   дела? ')).toBe('как дела')
  })
})

describe('dictation', () => {
  it('perfect match scores 100', () => {
    const r = dictation('меня зовут анна', 'Меня́ зову́т А́нна.')
    expect(r.score).toBe(100)
    expect(r.diff.every(d => d.ok)).toBe(true)
  })

  it('half wrong scores ~50 and marks diff', () => {
    const r = dictation('меня зовут', 'Меня зовут Анна')
    expect(r.score).toBeGreaterThan(0)
    expect(r.score).toBeLessThan(100)
    expect(r.diff.length).toBe(3)
    expect(r.diff[2].ok).toBe(false)
  })

  it('empty input scores 0', () => {
    expect(dictation('', 'Привет').score).toBe(0)
  })
})

describe('selfRate', () => {
  it('maps 0..3 to 0/35/70/100', () => {
    expect(selfRate(0)).toBe(0)
    expect(selfRate(1)).toBe(35)
    expect(selfRate(2)).toBe(70)
    expect(selfRate(3)).toBe(100)
  })
})

describe('sentenceMastery / videoScore', () => {
  it('averages available scores', () => {
    expect(sentenceMastery({ dictate: 80, recite: 60 })).toBe(70)
    expect(sentenceMastery({ dictate: 80 })).toBe(80)
    expect(sentenceMastery({})).toBeNull()
  })

  it('videoScore averages practiced sentences', () => {
    expect(videoScore({ 1: { dictate: 100 }, 2: { recite: 0 } })).toBe(50)
    expect(videoScore({})).toBe(0)
  })
})

describe('unlock logic', () => {
  const levelIds = { A1: ['a1_greet_01'], A2: [], B1: [], B2: [] }
  it('A1 always unlocked; higher levels need prev >= LEVEL_PASS', () => {
    expect(isLevelUnlocked('A1', {}, levelIds)).toBe(true)
    expect(isLevelUnlocked('A2', {}, levelIds)).toBe(false)
  })

  it('level unlocks when prev level mastery >= 60', () => {
    const progress = { a1_greet_01: { done: true, score: 80 } }
    expect(levelMastery(levelIds.A1, progress)).toBe(80)
    expect(isLevelUnlocked('A2', progress, levelIds)).toBe(true)
  })

  it('video i+1 unlocked only when video i done', () => {
    const ids = { A1: ['a1_greet_01', 'a1_intro_01'] }
    const progress = { a1_greet_01: { done: true, score: 90 } }
    expect(isVideoUnlocked('A1', 0, progress, ids)).toBe(true)
    expect(isVideoUnlocked('A1', 1, progress, ids)).toBe(true)
    expect(isVideoUnlocked('A1', 2, {}, ids)).toBe(false)
  })
})
