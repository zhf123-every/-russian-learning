export function getRuVoice() {
  if (!('speechSynthesis' in window)) return null
  const voices = window.speechSynthesis.getVoices()
  return voices.find(v => /ru/i.test(v.lang)) || null
}

export function speak(text, { rate = 1, voice = null, onStart, onEnd } = {}) {
  if (!('speechSynthesis' in window)) return
  const u = new SpeechSynthesisUtterance(text)
  if (voice) u.voice = voice
  u.lang = voice?.lang || 'ru-RU'
  u.rate = rate
  if (onStart) u.onstart = onStart
  if (onEnd) u.onend = onEnd
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(u)
}

export function cancelSpeech() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

export function speakAll(sentences, { from = 0, rate = 1, voice = null, onIndex, onDone } = {}) {
  let i = from
  const next = () => {
    if (i >= sentences.length) { onDone?.(); return }
    onIndex?.(i)
    speak(sentences[i].russian, {
      rate, voice,
      onEnd: () => { i++; next() },
    })
  }
  next()
}

export function loopSentence(sentences, i, times = 3, { rate = 1, voice = null, onIndex, onDone } = {}) {
  let n = 0
  const next = () => {
    if (n >= times) { onDone?.(); return }
    n++
    onIndex?.(i)
    speak(sentences[i].russian, { rate, voice, onEnd: next })
  }
  next()
}
