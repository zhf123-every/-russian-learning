import { describe, it, expect } from 'vitest'
import { callAI, parseAIJSON, chat } from './ai'
import { norm as normSrt } from './srt'

describe('parseAIJSON', () => {
  it('parses plain JSON string', () => {
    const result = parseAIJSON('{"sentences":["Привет."]}')
    expect(result).toEqual({ sentences: ['Привет.'] })
  })

  it('parses markdown-wrapped JSON', () => {
    const result = parseAIJSON('```json\n{"sentences":["Привет."]}\n```')
    expect(result).toEqual({ sentences: ['Привет.'] })
  })

  it('parses JSON with extra text', () => {
    const result = parseAIJSON('Вот ответ: {"sentences":["Привет."]} конец')
    expect(result).toEqual({ sentences: ['Привет.'] })
  })

  it('returns null for invalid JSON', () => {
    expect(parseAIJSON('not json')).toBeNull()
    expect(parseAIJSON('')).toBeNull()
  })

  it('returns null for null input', () => {
    expect(parseAIJSON(null)).toBeNull()
  })
})

describe('norm from srt', () => {
  it('lowercases and strips punctuation', () => {
    expect(normSrt('Привет!')).toBe('привет')
    expect(normSrt('Как, дела?')).toBe('как дела')
    expect(normSrt('«Привет»')).toBe('привет')
  })
})

describe('callAI (integration)', () => {
  it.skip('requires network', async () => {
    const result = await callAI([{ role: 'user', content: 'test' }])
    expect(typeof result).toBe('string')
  })
})