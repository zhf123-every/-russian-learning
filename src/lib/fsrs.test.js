import { describe, it, expect } from 'vitest'
import { newCard, review, isDue, RATING, serializeCard, deserializeCard } from './fsrs'

describe('fsrs wrapper', () => {
  it('newCard is due immediately', () => {
    const c = newCard()
    expect(isDue(c, new Date())).toBe(true)
  })

  it('review pushes due into future', () => {
    const c = review(newCard(), RATING.good)
    expect(isDue(c, new Date())).toBe(false)
  })

  it('review again keeps due near now', () => {
    const c = review(newCard(), RATING.again)
    expect(isDue(c, new Date())).toBe(true)
  })

  it('serialize/deserialize round-trips due as Date', () => {
    const c = review(newCard(), RATING.good)
    const rt = deserializeCard(JSON.parse(JSON.stringify(serializeCard(c))))
    expect(rt.due instanceof Date).toBe(true)
    expect(rt.due.getTime()).toBeCloseTo(c.due.getTime(), -2)
  })
})
