import { useEffect, useRef, useState } from 'react'
import { useVocabStore } from '../store/vocabStore'

export default function WordPop({ word, x, y, onClose }) {
  const ref = useRef(null)
  const addWord = useVocabStore(s => s.addWord)
  const [chinese, setChinese] = useState('')

  useEffect(() => {
    const onDoc = e => { if (ref.current && !ref.current.contains(e.target)) onClose() }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [onClose])

  const add = () => {
    addWord({ word, lemma: word.replace(/[́̀]/g, ''), chinese: chinese || '（待释义）', source: 'sentence' })
    onClose()
  }

  return (
    <div className="word-pop" ref={ref} style={{ left: x, top: y }}>
      <div className="w-head ru">{word}</div>
      <div className="w-body">
        <input
          placeholder="释义（可选，AI 翻译见 Task 13）"
          value={chinese}
          onChange={e => setChinese(e.target.value)}
          style={{ width: '100%', padding: '6px 8px', border: '1px solid var(--border2)', borderRadius: 6 }}
        />
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn sm primary" onClick={add}>＋ 加入生词</button>
      </div>
    </div>
  )
}
