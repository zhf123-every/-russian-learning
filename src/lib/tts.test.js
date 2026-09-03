import { describe, it, expect, vi, beforeEach } from 'vitest'

function mockTTS() {
  const utterances = []
  let onStart = null, onEnd = null
  const speak = vi.fn((u) => {
    utterances.push(u)
    u.onstart = u.onstart || (() => {})
    u.onend = u.onend || (() => {})
    // 记录当前回调便于测试里手动触发
    onStart = () => u.onstart()
    onEnd = () => u.onend()
  })
  const cancel = vi.fn()
  globalThis.speechSynthesis = { speak, cancel, getVoices: vi.fn(() => []) }
  globalThis.SpeechSynthesisUtterance = class {
    constructor(text) { this.text = text; this.rate = 1; this.voice = null }
  }
  return { speak, cancel, utterances, fireStart: () => onStart?.(), fireEnd: () => onEnd?.() }
}

describe('tts', () => {
  beforeEach(() => { vi.resetModules() })

  it('speak calls speechSynthesis.speak with utterance', async () => {
    const m = mockTTS()
    const { speak } = await import('./tts')
    speak('привет', { rate: 1 })
    expect(m.speak).toHaveBeenCalledTimes(1)
  })

  it('speakAll fires onIndex in order and onDone at end', async () => {
    const m = mockTTS()
    const { speakAll } = await import('./tts')
    const idx = []
    const done = vi.fn()
    speakAll([{ russian: 'a' }, { russian: 'b' }], { from: 0, onIndex: i => idx.push(i), onDone: done })
    expect(idx).toEqual([0])
    m.fireEnd()
    expect(idx).toEqual([0, 1])
    m.fireEnd()
    expect(done).toHaveBeenCalledTimes(1)
  })

  it('cancelSpeech calls cancel', async () => {
    const m = mockTTS()
    const { cancelSpeech } = await import('./tts')
    cancelSpeech()
    expect(m.cancel).toHaveBeenCalled()
  })
})
