import { useState } from 'react'
import WordPop from './WordPop'

export default function SentenceBox({ sentence, revealed }) {
  const [pop, setPop] = useState(null)

  if (!revealed) return <div className="sentence-box"><div className="cover">🔇 原文已隐藏</div></div>

  const html = sentence.russian
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .split(/\s+/)
    .map(w => `<span class="w" data-word="${w}">${w}</span>`)
    .join(' ')

  const onClick = (e) => {
    const el = e.target.closest('.w')
    if (el) setPop({ word: el.dataset.word, x: e.clientX, y: e.clientY })
  }

  return (
    <>
      <div className="sentence-box" onClick={onClick}>
        <div className="txt ru" dangerouslySetInnerHTML={{ __html: html }} />
      </div>
      {pop && <WordPop word={pop.word} x={pop.x} y={pop.y} onClose={() => setPop(null)} />}
    </>
  )
}
