import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from '../lib/toast'

const CATEGORIES = ['shopping', 'daily', 'vlog', 'speech', 'intro', 'campus', 'work', 'transport']
const LEVELS = ['A1', 'A2', 'B1', 'B2']

export default function ContributeModal({ onClose, onSubmit }) {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    title: '',
    category: 'shopping',
    level: 'A1',
    videoUrl: '',
    description: ''
  })
  const [submitting, setSubmitting] = useState(false)

  const handleChange = (field) => (e) => {
    setForm(prev => ({ ...prev, [field]: e.target.value }))
  }

  const handleSubmit = async () => {
    if (!form.title || !form.videoUrl) {
      toast('请填写标题和视频链接')
      return
    }
    setSubmitting(true)
    try {
      const id = 'square_' + Date.now()
      const author = '匿名用户'
      const thumbnail = `https://picsum.photos/seed/${id}/400/280`
      const posterUrl = `https://picsum.photos/seed/${id}/1280/720`
      const views = 0
      const createdAt = Date.now()

      // 从视频链接抓取字幕并断句
      let sentences = []
      let fetchError = ''
      try {
        const r = await fetch('/api/subs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: form.videoUrl })
        })
        const j = await r.json()
        if (j.ok && j.text) {
          const { parseTextToSentences } = await import('../lib/srt')
          const { sentences: parsed } = parseTextToSentences(j.text)
          sentences = parsed.map((s, i) => ({ id: i + 1, russian: s.text, chinese: '' }))
        } else {
          fetchError = j.error || '未知错误'
        }
      } catch (e) {
        fetchError = e.message
      }

      const payload = {
        id,
        title: form.title,
        category: form.category,
        level: form.level,
        videoUrl: form.videoUrl,
        description: form.description,
        thumbnail,
        posterUrl,
        sentences,
        author,
        views,
        createdAt,
        tags: [form.category, form.level]
      }

      await onSubmit(payload)
      toast(fetchError ? '已投稿，但字幕抓取失败：' + fetchError : '投稿成功！')
      onClose()
      navigate('/square')
    } catch (e) {
      toast('投稿失败：' + (e.message || '请重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <h2>投稿素材</h2>
        <p className="hint">请提供视频链接和分类，我们将在审核后发布到学习广场</p>

        <div className="field">
          <label>标题</label>
          <input value={form.title} onChange={handleChange('title')} placeholder="例如：莫斯科地铁站的美丽" />
        </div>

        <div className="field">
          <label>分类</label>
          <select value={form.category} onChange={handleChange('category')}>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div className="field">
          <label>难度</label>
          <select value={form.level} onChange={handleChange('level')}>
            {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>

        <div className="field">
          <label>视频链接</label>
          <input
            value={form.videoUrl}
            onChange={handleChange('videoUrl')}
            placeholder="https://www.youtube.com/watch?v=... 或 Bilibili"
          />
        </div>

        <div className="field">
          <label>描述（可选）</label>
          <textarea
            value={form.description}
            onChange={handleChange('description')}
            placeholder="补充说明，比如场景、学习目标等"
            rows={3}
          />
        </div>

        <div className="mfoot">
          <button className="btn" onClick={onClose} disabled={submitting}>取消</button>
          <button className="btn primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? '提交中...' : '投稿'}
          </button>
        </div>
      </div>
    </div>
  )
}