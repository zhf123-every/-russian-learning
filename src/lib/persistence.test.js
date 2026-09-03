import { describe, it, expect, beforeEach, vi } from 'vitest'
import { loadLS, saveLS, LS } from './persistence'

describe('persistence', () => {
  beforeEach(() => localStorage.clear())

  it('loadLS returns default when key missing', () => {
    expect(loadLS(LS.progress, {})).toEqual({})
  })

  it('saveLS then loadLS round-trips objects', () => {
    saveLS(LS.progress, { a: 1 })
    expect(loadLS(LS.progress, {})).toEqual({ a: 1 })
  })

  it('loadLS returns default on corrupt JSON', () => {
    localStorage.setItem(LS.progress, '{bad json')
    expect(loadLS(LS.progress, { def: true })).toEqual({ def: true })
  })

  it('saveLS swallows quota errors without throwing', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(() => saveLS(LS.progress, { x: 1 })).not.toThrow()
  })

  it('keys use rlearn_v1 prefix', () => {
    expect(LS.progress).toBe('rlearn_v1_progress')
    expect(LS.vocab).toBe('rlearn_v1_vocab')
  })
})
