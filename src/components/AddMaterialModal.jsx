import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { splitText } from '../lib/splitter'
import { useCourseStore } from '../store/courseStore'
import { toast } from '../lib/toast'

export default function AddMaterialModal({ onClose }) {
  const navigate = useNavigate()
  const addMaterial = useCourseStore(s => s.addMaterial)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')

  const save = () => {
    const sents = splitText(text).map((russian, i) => ({ id: i + 1, russian }))
    if (!sents.length) { toast('请输入俄语文本'); return }
    const id = 'custom_' + Date.now().toString(36)
    const wordCount = sents.reduce((n, s) => n + s.russian.trim().split(/\s+/).length, 0)
    addMaterial({
      id,
      title: title.trim() || '自定义文本',
      sentences: sents,
      createdAt: Date.now(),
      thumbnail: 'https://picsum.photos/seed/' + id + '/400/280',
      posterUrl: 'https://picsum.photos/seed/' + id + '/1280/720',
      tags: ['自定义'],
      duration: '—',
      words: wordCount,
      level: '自定义',
    })
    navigate('/study/' + id)
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>＋ 添加资料</h2>
        <p className="hint">粘贴俄语文本，自动断句后进入 TTS 学习（无视频、无需字幕）。</p>
        <div className="field">
          <label>标题（可选）</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：俄语日常对话" />
        </div>
        <div className="field">
          <label>俄语文本</label>
          <textarea rows={8} value={text} onChange={e => setText(e.target.value)} placeholder="粘贴俄语文本…" />
        </div>
        <div className="mfoot">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={save}>保存并开始学习</button>
        </div>
      </div>
    </div>
  )
}
