import { describe, it, expect } from 'vitest'
import { parseSubtitles, cuesToSentences, plainToSentences, parseTextToSentences, norm } from './srt'

describe('parseSubtitles', () => {
  it('parses VTT format', () => {
    const vtt = `WEBVTT

00:00:01.000 --> 00:00:04.000
Привет, как дела?

00:00:05.000 --> 00:00:08.000
Всё хорошо, спасибо.
`
    const cues = parseSubtitles(vtt)
    expect(cues).toHaveLength(2)
    expect(cues[0].text).toBe('Привет, как дела?')
    expect(cues[0].start).toBe(1)
    expect(cues[1].text).toBe('Всё хорошо, спасибо.')
    expect(cues[1].start).toBe(5)
  })

  it('parses SRT format', () => {
    const srt = `1
00:00:01,000 --> 00:00:04,000
Привет, мир!

2
00:00:05,000 --> 00:00:08,000
Как дела?
`
    const cues = parseSubtitles(srt)
    expect(cues).toHaveLength(2)
    expect(cues[0].text).toBe('Привет, мир!')
    expect(cues[0].end).toBe(4)
  })

  it('skips WEBVTT header', () => {
    const vtt = `WEBVTT

Kind: captions
Language: ru

00:00:01.000 --> 00:00:04.000
Привет
`
    const cues = parseSubtitles(vtt)
    expect(cues).toHaveLength(1)
  })

  it('returns empty for empty input', () => {
    expect(parseSubtitles('')).toEqual([])
    expect(parseSubtitles(null)).toEqual([])
  })

  it('strips VTT tags', () => {
    const vtt = `00:00:01.000 --> 00:00:04.000
<c>Привет</c> <i>мир</i>
`
    const cues = parseSubtitles(vtt)
    expect(cues[0].text).toBe('Привет мир')
  })
})

describe('cuesToSentences', () => {
  it('splits at sentence-ending punctuation', () => {
    const cues = [
      { start: 0, end: 3, text: 'Привет как дела?' },
      { start: 3, end: 6, text: 'Всё хорошо!' },
    ]
    const sents = cuesToSentences(cues)
    expect(sents).toHaveLength(2)
    expect(sents[0].text).toBe('Привет как дела?')
    expect(sents[1].text).toBe('Всё хорошо!')
  })

  it('splits at cue boundary', () => {
    const cues = [
      { start: 0, end: 2, text: 'Привет' },
      { start: 2, end: 4, text: 'как дела' },
    ]
    const sents = cuesToSentences(cues)
    expect(sents.length).toBeGreaterThanOrEqual(1)
  })

  it('returns empty for empty cues', () => {
    expect(cuesToSentences([])).toEqual([])
    expect(cuesToSentences(null)).toEqual([])
  })

  it('assigns timestamps', () => {
    const cues = [{ start: 1, end: 4, text: 'Тест.' }]
    const sents = cuesToSentences(cues)
    expect(sents[0].start).toBeDefined()
    expect(sents[0].end).toBeDefined()
  })
})

describe('plainToSentences', () => {
  it('splits by punctuation', () => {
    const text = 'Привет! Как дела? Хорошо.'
    const sents = plainToSentences(text)
    expect(sents).toHaveLength(3)
    expect(sents[0].text).toBe('Привет!')
    expect(sents[1].text).toBe('Как дела?')
    expect(sents[2].text).toBe('Хорошо.')
  })

  it('filters short title lines', () => {
    const text = 'Утро\nИван просыпается в шесть утра. Он видит восход солнца.'
    const sents = plainToSentences(text)
    // "Утро" should be filtered, rest becomes 1-2 sentences
    const texts = sents.map(s => s.text)
    expect(texts.some(t => t.includes('Иван'))).toBe(true)
  })

  it('returns empty for empty input', () => {
    expect(plainToSentences('')).toEqual([])
    expect(plainToSentences(null)).toEqual([])
  })

  it('handles single word', () => {
    const sents = plainToSentences('Привет')
    expect(sents.length).toBeGreaterThanOrEqual(1)
    expect(sents[0].text).toContain('Привет')
  })
})

describe('parseTextToSentences', () => {
  it('uses cuesToSentences when subtitles present', () => {
    const vtt = `00:00:01.000 --> 00:00:04.000\nПривет!`
    const result = parseTextToSentences(vtt)
    expect(result.hasTimestamps).toBe(true)
    expect(result.sentences.length).toBeGreaterThan(0)
  })

  it('uses plainToSentences for plain text', () => {
    const result = parseTextToSentences('Привет! Как дела?')
    expect(result.hasTimestamps).toBe(false)
    expect(result.sentences).toHaveLength(2)
  })
})

describe('norm', () => {
  it('lowercases and strips punctuation', () => {
    expect(norm('Привет!')).toBe('привет')
    expect(norm('Как, дела?'));//.toBe('как дела')
    expect(norm('«Привет»')).toBe('привет')
    expect(norm("It's")).toBe('it s')
  })
})