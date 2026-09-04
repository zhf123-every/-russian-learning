import { useState } from 'react'
import { useVocabStore } from '../store/vocabStore'
import { useNavigate } from 'react-router-dom'

export default function AddVocabModal({ onClose }) {
  const navigate = useNavigate()
  const addVocab = useVocabStore(s => s.add)

  const [word, setWord] = useState('')
  const [chinese, setChinese] = useState('')
  const [reading, setReading] = useState('')
  const [pos, setPos] = useState('')
  const [file, setFile] = useState(null)

  const loadFromFile = (f) => {
    const r = new FileReader()
    r.onload = () => {
      const text = r.result
      const lines = text.split(/\r?\n/).filter(l => l.trim() && !l.startsWith('#'))
      const [first, ...rest] = lines
      if (first) {
        const [w, c] = first.split('\t').map(x => x.trim())
        if (w && c) {
          setWord(w)
          setChinese(c)
        }
      }
      if (rest.length > 0) {
        const content = rest.map(l => {
          const [w, c] = l.split('\t').map(x => x.trim())
          return w && c ? `**${w}** — ${c}` : ''
        }).join('\n')
        const blob = new Blob([content], { type: 'text/markdown' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'vocab.md'
        a.click()
        URL.revokeObjectURL(url)
        toast('已导出 vocab.md，可替换内容后导入')
      }
    }
    r.readAsText(f)
  }

  const save = () => {
    if (!word.trim()) { toast('请输入俄语单词'); return }
    if (!chinese.trim()) { toast('请输入中文翻译'); return }
    addVocab({ id: word.trim(), word: word.trim(), chinese: chinese.trim(), reading: reading.trim(), pos: pos.trim(), addedAt: Date.now() })
    toast('已加入生词本')
    navigate('/vocab')
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>＋ 加入生词</h2>
        <p className="hint">填写俄语单词及其中文翻译，点击「加入生词本」后，自动进入「生词本」页面进行复习。</p>

        <div className="field">
          <label>俄语单词</label>
          <input value={word} onChange={e => setWord(e.target.value)} placeholder="例如：стол" />
        </div>

        <div className="field">
          <label>中文翻译</label>
          <input value={chinese} onChange={e => setChinese(e.target.value)} placeholder="例如：桌子" />
        </div>

        <div className="field">
          <label>拼写/读音（可选）</label>
          <input value={reading} onChange={e => setReading(e.target.value)} placeholder="例如：стол" />
        </div>

        <div className="field">
          <label>词性（可选）</label>
          <input value={pos} onChange={e => setPos(e.target.value)} placeholder="例如：名词" />
        </div>

        <div className="field">
          <label>从文件导入（支持 TSV 格式）</label>
          <input type="file" accept=".txt,.tsv,.md" onChange={e => loadFromFile(e.target.files?.[0])} />
        </div>

        <div className="mfoot">
          <button className="btn" onClick={onClose}>关闭</button>
          <button className="btn primary" onClick={save}>加入生词本</button>
        </div>
      </div>
    </div>
  )
}