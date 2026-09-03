import { useState } from 'react'
import { useVocabStore } from '../store/vocabStore'
import { RATING } from '../lib/fsrs'

const GRADES = [
  { r: RATING.again, label: '忘记' }, { r: RATING.hard, label: '困难' },
  { r: RATING.good, label: '记得' }, { r: RATING.easy, label: '轻松' }
]

export default function Vocab() {
  const cards = useVocabStore(s => s.cards)
  const due = useVocabStore(s => s.dueCards())
  const review = useVocabStore(s => s.review)
  const [show, setShow] = useState(false)
  const [i, setI] = useState(0)

  if (due.length === 0) {
    return <div className="empty"><div className="big">🎉</div><h1>今天没有待复习的生词</h1><p>共 {cards.length} 个生词。</p></div>
  }

  const card = due[i] || due[0]
  const rate = (r) => { review(card.id, r); setShow(false); setI(0) }

  return (
    <div className="modal-mask" style={{ position: 'static', background: 'none', padding: 24 }}>
      <div className="modal" style={{ maxWidth: 460, margin: '0 auto' }}>
        <h2>生词复习</h2>
        <div className="srs-card">
          <div className="q"><span className="w ru">{card.word}</span></div>
          {show && <div className="a">{card.chinese}</div>}
          {!show && <button className="btn primary" onClick={() => setShow(true)}>显示答案</button>}
          {show && (
            <div className="srs-grades">
              {GRADES.map(g => <button key={g.label} className="grade" onClick={() => rate(g.r)}>{g.label}</button>)}
            </div>
          )}
        </div>
        <div className="srs-stats">今日待复习 {due.length} 个 · 共 {cards.length} 个生词</div>
      </div>
    </div>
  )
}
